"""Offline, authorization-scoped analysis of the Synthetic XY case.

No external models, network calls, CRM writes or PII are required. All text
sources are untrusted. Outputs contain only household IDs and evidence pointers.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .analytics import PortfolioAnalyzer
from .domain import AS_OF, Holding
from .security import AccessGateway, Forbidden, InMemoryAudit, Principal

TABLE_COLUMNS = {
    'households': {'hushall_id','personnummer','namn','epost','telefon','radgivare_id','senaste_mote','omprovning_senast','likvida_medel_sek','isk_sek','kapitalforsakring_sek','tjanstepension_kand','riskprofil','lamplighet_komplett'},
    'holdings': {'hushall_id','kontotyp','isin','instrument','varde_sek','arlig_avgift_pct','per_datum'},
    'meetings': {'mote_id','hushall_id','datum','radgivare_id','typ','anteckning'},
    'advisors': {'radgivare_id','namn','roll','enhet','behorighet_hushall'},
}
TRANSCRIPTS = re.compile(r'^T\d+_(H\d+)_\d{4}-\d{2}-\d{2}\.txt$')
TIMED = re.compile(r'^\[(\d{2}:\d{2}:\d{2})\] (Rådgivare|Kund): (.*)$')
INJECTION = re.compile(r'(?:NOTERING TILL AI|AI.SYSTEMET|systemmeddelande|ignorera tidigare instruktioner|write_client_record|sätt riskprofil|markera lämplighet)', re.I)
GUARANTEE = re.compile(r'(?:nästan garanterat|garanterad avkastning|almost guaranteed)', re.I)
LOWER_RISK = re.compile(r'(?:vill vara försiktig|vill minska risken|inte längre|vill inte ha allt i aktier)', re.I)

class DataContractError(ValueError):
    pass

def money(value: str, label: str, nullable: bool = False) -> Decimal | None:
    if not value.strip() and nullable:
        return None
    try:
        number = Decimal(value.strip())
    except InvalidOperation as exc:
        raise DataContractError(f'{label}: invalid decimal') from exc
    if not number.is_finite() or number < 0:
        raise DataContractError(f'{label}: invalid nonnegative value')
    return number

def read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not required.issubset(reader.fieldnames or []):
            raise DataContractError(f'{path.name}: missing {sorted(required - set(reader.fieldnames or []))}')
        rows = list(reader)
    if any(None in r or any(v is None for v in r.values()) for r in rows):
        raise DataContractError(f'{path.name}: malformed CSV row')
    return rows

@dataclass(frozen=True)
class Finding:
    code: str
    household_id: str
    severity: str
    evidence: tuple[str, ...]
    detail: str

class CaseRepository:
    """Internal raw store. Never pass this object to an LLM or serialize its rows."""
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.rows = {name: read_csv(self.folder / f'{name}.csv', required)
                     for name, required in TABLE_COLUMNS.items()}
        self.households = {r['hushall_id']: r for r in self.rows['households']}
        self.advisors = {r['radgivare_id']: r for r in self.rows['advisors']}
        if len(self.households) != len(self.rows['households']):
            raise DataContractError('duplicate household ID')
        if len(self.advisors) != len(self.rows['advisors']):
            raise DataContractError('duplicate advisor ID')
        if len({r['mote_id'] for r in self.rows['meetings']}) != len(self.rows['meetings']):
            raise DataContractError('duplicate meeting ID')
        self.transcripts = {}
        for p in self.folder.glob('T*_H*_*.txt'):
            m = TRANSCRIPTS.fullmatch(p.name)
            if m:
                self.transcripts[m.group(1)] = self.transcripts.get(m.group(1), []) + [(p.name, p.read_text(encoding='utf-8'))]
        self._validate()

    def _validate(self):
        for name in ('holdings','meetings'):
            for row in self.rows[name]:
                if row['hushall_id'] not in self.households:
                    raise DataContractError(f'{name}: unknown household')
        for row in self.rows['households']:
            if row['radgivare_id'] not in self.advisors:
                raise DataContractError('unknown assigned advisor')
            for field in ('likvida_medel_sek','isk_sek','kapitalforsakring_sek'):
                money(row[field], field)
            for field in ('senaste_mote','omprovning_senast'):
                date.fromisoformat(row[field])
            if row['riskprofil'] not in {'forsiktig','balanserad','offensiv',''}:
                raise DataContractError('invalid risk profile')
            if row['lamplighet_komplett'] not in {'ja','nej'}:
                raise DataContractError('invalid suitability flag')
        for row in self.rows['holdings']:
            if row['kontotyp'] not in {'ISK','KF'}:
                raise DataContractError('unknown account type')
            money(row['varde_sek'], 'varde_sek')
            money(row['arlig_avgift_pct'], 'arlig_avgift_pct', nullable=True)
            date.fromisoformat(row['per_datum'])
        for row in self.rows['meetings']:
            date.fromisoformat(row['datum'])
            if row['radgivare_id'] not in self.advisors:
                raise DataContractError('unknown meeting advisor')
        for advisor in self.advisors.values():
            allowed = set(filter(None, advisor['behorighet_hushall'].split(';')))
            if not allowed <= self.households.keys():
                raise DataContractError('permission references unknown household')
        for h in self.households.values():
            if h['hushall_id'] not in self.principal(h['radgivare_id']).allowed_households:
                raise DataContractError('assigned advisor lacks permission')

    def principal(self, advisor_id: str) -> Principal:
        if advisor_id not in self.advisors:
            raise Forbidden('Unknown advisor')
        return Principal(advisor_id, frozenset(filter(None, self.advisors[advisor_id]['behorighet_hushall'].split(';'))))

    def scoped(self, principal: Principal, household: str, gateway: AccessGateway):
        gateway.require(principal, household)
        if household not in self.households:
            raise Forbidden('Household unavailable')
        return (self.households[household],
                [r for r in self.rows['holdings'] if r['hushall_id'] == household],
                [r for r in self.rows['meetings'] if r['hushall_id'] == household],
                self.transcripts.get(household, []))

    def fingerprint(self) -> str:
        sha = hashlib.sha256()
        for p in sorted([*(self.folder / f'{name}.csv' for name in TABLE_COLUMNS), *self.folder.glob('T*_H*_*.txt')]):
            sha.update(p.name.encode()); sha.update(p.read_bytes())
        return sha.hexdigest()

class CaseAnalyzer:
    def __init__(self, repository: CaseRepository, gateway: AccessGateway):
        self.repo, self.gateway = repository, gateway
        self.portfolio = PortfolioAnalyzer()

    def analyze(self, principal: Principal, household_id: str) -> dict[str, Any]:
        household, holding_rows, meetings, transcripts = self.repo.scoped(principal, household_id, self.gateway)
        findings: list[Finding] = []
        def flag(code: str, severity: str, detail: str, *evidence: str):
            findings.append(Finding(code, household_id, severity, tuple(evidence), detail))
        holdings = [Holding(household_id, r['kontotyp'], r['isin'], money(r['varde_sek'],'varde_sek'),
                            money(r['arlig_avgift_pct'],'arlig_avgift_pct',nullable=True)) for r in holding_rows]
        portfolio = self.portfolio.summarize(household_id, holdings)
        cash = money(household['likvida_medel_sek'], 'cash')
        isk = money(household['isk_sek'], 'isk')
        kf = money(household['kapitalforsakring_sek'], 'kf')
        for account, reported in [('ISK',isk),('KF',kf)]:
            observed = portfolio.by_account_sek.get(account, Decimal(0))
            if observed != reported:
                flag('ACCOUNT_RECONCILIATION', 'warning', f'{account}: household={reported}, holdings={observed}', 'households.csv:'+household_id, 'holdings.csv:'+household_id)
        if portfolio.unknown_fee_value_sek:
            flag('MISSING_FEE', 'warning', 'Fee coverage incomplete; never assume zero', *(f"holdings.csv:{household_id}:{r['isin']}" for r in holding_rows if not r['arlig_avgift_pct'].strip()))
        if not household['riskprofil']:
            flag('MISSING_RISK_PROFILE','high','Recorded risk profile is missing','households.csv:'+household_id)
        if household['lamplighet_komplett'] == 'nej':
            flag('SUITABILITY_INCOMPLETE','high','Suitability marked incomplete','households.csv:'+household_id)
        if date.fromisoformat(household['omprovning_senast']) < AS_OF:
            flag('REVIEW_OVERDUE','warning','Review due date precedes case as-of date','households.csv:'+household_id)
        if household['tjanstepension_kand'] in ('nej','okand'):
            flag('PENSION_DATA_GAP','info','Occupational pension not confirmed','households.csv:'+household_id)
        for r in holding_rows:
            if date.fromisoformat(r['per_datum']) > AS_OF:
                flag('FUTURE_VALUATION','high','Holding valuation occurs after as-of date',f"holdings.csv:{household_id}:{r['isin']}")
            if not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{10}',r['isin']):
                flag('ISIN_FORMAT','warning','ISIN format invalid',f"holdings.csv:{household_id}:{r['isin']}")
        source_count = 0
        for meeting in meetings:
            source_count += 1
            source = 'meetings.csv:'+meeting['mote_id']
            if date.fromisoformat(meeting['datum']) > AS_OF:
                flag('FUTURE_MEETING', 'high', 'Meeting is dated after the dataset as-of date', source)
            if INJECTION.search(meeting['anteckning']):
                flag('PROMPT_INJECTION','critical','Untrusted CRM instruction quarantined',source)
            elif LOWER_RISK.search(meeting['anteckning']):
                flag('LOWER_RISK_EXPRESSED', 'high', 'Meeting note records a request to reduce risk; review profile', source)
        if date.fromisoformat(household['senaste_mote']) > AS_OF:
            flag('FUTURE_LAST_MEETING', 'high', 'Recorded last meeting is after the dataset as-of date', 'households.csv:'+household_id)
        latest = max((m['datum'] for m in meetings if date.fromisoformat(m['datum']) <= AS_OF), default=None)
        if latest and latest > household['senaste_mote']:
            flag('STALE_LAST_MEETING', 'warning', f'Recorded last meeting {household["senaste_mote"]} precedes meeting {latest}', 'households.csv:'+household_id, 'meetings.csv:'+household_id)
        for filename, transcript in transcripts:
            source_count += 1
            risk_down = False
            guarantee = False
            for line in transcript.splitlines():
                m = TIMED.match(line)
                if not m: continue
                timestamp, speaker, text = m.groups()
                pointer = filename+':'+timestamp
                if INJECTION.search(text):
                    flag('PROMPT_INJECTION','critical','Untrusted transcript instruction quarantined',pointer)
                    continue  # Never extract risk intent from injected material.
                if speaker == 'Kund' and LOWER_RISK.search(text) and not re.search(r'samma som förut', text, re.I):
                    risk_down = True
                    flag('LOWER_RISK_EXPRESSED','high','Client expressed caution / desire for lower risk',pointer)
                if speaker == 'Rådgivare' and GUARANTEE.search(text):
                    guarantee = True
                    flag('RETURN_ASSURANCE','critical','Advisor describes future returns as near-guaranteed',pointer)
                if speaker == 'Kund' and re.search(r'(?:350 000|renovera köket)',text,re.I):
                    flag('PLANNED_EXPENDITURE','info','Client discusses future renovation expenditure; verify before use',pointer)
                if speaker == 'Kund' and re.search(r'(?:fått ett barn till|gått ner i tid)',text,re.I):
                    flag('LIFE_EVENT','info','Changed family circumstances / household income',pointer)
            if risk_down and household['riskprofil'] == 'offensiv':
                flag('RISK_PROFILE_CONFLICT','high','Recorded aggressive risk profile conflicts with client statement','households.csv:'+household_id,filename)
            if risk_down and guarantee:
                flag('CONDUCT_RISK_CONFLICT','critical','Return assurance conflicts with expressed client caution',filename)
        total_assets = cash + isk + kf
        def dec(v): return None if v is None else str(v)
        return {
            'household_id':household_id,'as_of':AS_OF.isoformat(),'data_sha256':self.repo.fingerprint(),
            'recorded_risk_profile':household['riskprofil'],
            'suitability_complete':household['lamplighet_komplett']=='ja',
            'assets':{'cash_sek':dec(cash),'isk_sek':dec(isk),'kf_sek':dec(kf),'total_sek':dec(total_assets)},
            'holdings':{'count':len(holdings),'valuation_sek':dec(portfolio.total_value_sek),
                        'annual_fee_known_sek':dec(portfolio.annual_fee_sek_known),
                        'fee_known_exposure_sek':dec(portfolio.known_fee_value_sek),
                        'fee_unknown_exposure_sek':dec(portfolio.unknown_fee_value_sek),
                        'known_exposure_weighted_fee_pct':dec(portfolio.weighted_fee_pct),
                        'full_fee_coverage':portfolio.complete_fee_coverage,
                        'holding_row_hhi':dec(portfolio.concentration_hhi)},
            'untrusted_sources_examined':source_count,
            'findings':[asdict(f) for f in findings],
            'write_actions':[],
        }

def analyze_folder(folder: Path, advisor_id: str, household_id: str) -> dict[str, Any]:
    repo = CaseRepository(folder)
    principal = repo.principal(advisor_id)  # CLI demo only; production identity must be authenticated.
    return CaseAnalyzer(repo, AccessGateway(InMemoryAudit())).analyze(principal, household_id)
