import pytest
import shlex
import os
from partfinder import main, util, scheme, analysis_method, config, alignment, results, reporter


def test_aic():
    '''This test should pass'''
    HERE = os.path.abspath(os.path.dirname(__file__))
    full_path = os.path.join(HERE, "aictest")
    main.call_main("morphology", '--no-ml-tree --min-subset-size 1 --raxml "%s"' % full_path)
    new_file = os.path.join(full_path, "analysis/best_scheme.txt")
    txt = open(new_file)
    file_obj = txt.readlines()
    for x in file_obj:
        x = x.strip()
        if "Scheme AIC" in x:
            line = x.split(':')
            numspace = line[1]
            num = numspace.strip()
            num = float(num)
            num = int(num)
            assert num == 38
