# lcsrs

A CLI for LeetCode practice tracking with a plan order + spaced repetition.

```
# first time
lc init
lc import plan.txt
lc show

# daily
lc open
lc done 1011 good
lc history --n 10
lc stats

# move NEW cursor (start from the middle)
lc cursor set 1011
# optional: seed earlier problems into REVIEW (due now)
lc mark-done-before 1011 --force
