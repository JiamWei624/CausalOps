"""Run the original challenges with the current service and V1.3 transport."""
from causalops.evaluation.v12.__main__ import main

if __name__=='__main__':
    main(worker_module='causalops.evaluation.v13.attempt')
