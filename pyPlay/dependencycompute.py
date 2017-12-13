dependencyGraph = [
    {
        "id": "a"
    },
    {
        "id": "b",
        "dependsOn": ["a"]
    },
    {
        "id": "c",
        "dependsOn": ["b"]
    },
    {
        "id": "d",
        "dependsOn": ["e"]
    },
    {
        "id": "e",
        "dependsOn": ["b", "c"]
    },
    {
        "id": "f",
        "dependsOn": ["d", "e", "g"]
    },
    {
        "id": "g"
    }
]

# stores the node's values. e,g, "b": 24
values = {}


def recompute(node, val):
    values[node] = val
    # find nodes that depends on the input node
    nodes = [x for x in dependencyGraph if "dependsOn" in x and node in x["dependsOn"]]
    # calculate values of the found nodes
    for n in nodes:
        values[n["id"]] = sum(map(lambda x: values[x], n["dependsOn"]))
        print(values)


recompute("b", 24)
