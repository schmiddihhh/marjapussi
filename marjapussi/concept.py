from collections import defaultdict


class Concept:
    """
    This class encodes all knowledge an agent has aboutxD that might be cool!
    a game. Concepts can be "basic" or "dependent".
    Basic concepts are set by the agent's code, for example
    how probable certain combinations of cards are, or
    which provoking steps a player does.
    """
    def __init__(self, name: str, properties: dict, dependencies: list = None, weights: list[float] = None,
                 value: float = 0.):
        # TODO weight function (-> linear) or non-linear
        self._name = name
        self._properties = properties
        if not dependencies:
            dependencies = []
        self.dependencies = dependencies  # these are names of other concepts
        self.value = value
        if value > 1:
            self.value = 1
        if not weights:
            self.weights = [1.] * len(dependencies)
        elif len(dependencies) != len(weights):
            raise ValueError("The dependencies and weights must be of the same length.")
        # TODO Check if dependency is self dependant and raise error

    @property
    def name(self):
        return self._name

    @property
    def properties(self):
        return self._properties

    def evaluate(self, lazy: bool = False) -> float:
        """
        Concepts are not evaluated until needed.
        TODO:
         - cache calculations
         - invalidate cache upon change
         - when probabilities change re-evaluate in a background
        """
        if self.dependencies and not lazy:
            return sum(x * y for x, y in zip(self.dependencies, self.weights))
        else:
            return self.value


class ConceptStore:
    def __init__(self):
        self.dict_by_name = {}
        self.dict_by_properties = defaultdict(lambda: defaultdict(set))

    def add(self, concept: Concept) -> None:
        self.dict_by_name[concept.name] = concept
        for prop, value in concept.properties.items():
            self.dict_by_properties[prop][value].add(concept)

    def remove(self, name):
        obj = self.dict_by_name.get(name)
        if obj is not None:
            # Remove from dict_by_name
            del self.dict_by_name[name]
            # Remove from dict_by_properties
            for prop, value in obj.properties.items():
                self.dict_by_properties[prop][value].remove(obj)
                # If this was the last concept with this property value, remove the set
                if not self.dict_by_properties[prop][value]:
                    del self.dict_by_properties[prop][value]
                # If this was the last concept for this property, remove the property
                if not self.dict_by_properties[prop]:
                    del self.dict_by_properties[prop]

    def get_by_name(self, name: str) -> Concept | None:
        return self.dict_by_name.get(name)

    def get_all_by_properties(self, properties: dict) -> set[Concept]:
        matching_concepts = set(self.dict_by_name.values())
        for prop, value in properties.items():
            property_objects = self.dict_by_properties[prop].get(value, set())
            matching_concepts &= property_objects  # intersect with the current matching concepts
        return matching_concepts
    
    def __str__(self):
        return str([(concept.name, concept.value) for concept in self.dict_by_name.values()])
