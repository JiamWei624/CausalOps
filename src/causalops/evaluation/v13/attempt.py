"""Use the frozen V1.2 operator protocol, changing only the live transport adapter."""
import os
import argparse
from pathlib import Path
from causalops.evaluation.v12 import attempt
from .capture import Metered


def main():
    p=argparse.ArgumentParser()
    p.add_argument('folder',type=Path)
    p.add_argument('case',choices=list(attempt.CASES))
    p.add_argument('mode',choices=['local','deepseek'])
    args=p.parse_args()
    if args.folder.exists() or Path(os.environ['CAUSALOPS_HOME']).resolve()!=(args.folder/'work').resolve():
        p.error('须使用独立工作区')
    args.folder.mkdir(parents=True)
    attempt.Metered=Metered
    attempt.run(args.folder,args.case,args.mode)


if __name__=='__main__':main()
