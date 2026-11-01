"""Local case-analysis CLI. Advisor identity is a demo argument, NOT authentication."""
import argparse
import json
from pathlib import Path
from .case import analyze_folder

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--advisor', required=True)
    p.add_argument('--household', required=True)
    args = p.parse_args()
    print(json.dumps(analyze_folder(args.data,args.advisor,args.household),ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()
