from contextlib import contextmanager
from marjapussi.agent import Agent, test_agents
from marjapussi.game import MarjaPussi
from marjapussi.probabilistic_policy import ProbabilisticPolicy2

import random
import time

from marjapussi.policy import RandomPolicy
from marjapussi.policy import LittleSmartPolicy


# from policy2 import AlwaysProvokePolicy
# random.seed(2)

def main():
    # custom_rules = {
    #     "start_game_value": 115,
    #     "max_game_value": 140,
    # }
    custom_rules = {}
    with stop_watch('Testen'):
        test_agents(ProbabilisticPolicy2(), ProbabilisticPolicy2(), rounds=1, custom_rules=custom_rules, log_agent=False,
                    log_game='DEBUG')


@contextmanager
def stop_watch(name):
    start_time = time.time()
    yield
    elapsed_time = time.time() - start_time
    print('\u231B [{}] finished in {} ms'.format(
        name, int(elapsed_time * 1_000)))


if __name__ == '__main__':
    main()
