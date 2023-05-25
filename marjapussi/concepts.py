class Concept():
    def __init__(self, name : str, dependencies : list, weights: list[float] = None):
        self.name = name
        self.value = 0
        self.dependencies = dependencies
        if not weights:
            self.weights = [1.] * len(dependencies)

    def get(self):

