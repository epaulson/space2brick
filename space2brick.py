import csv
import argparse
from collections import defaultdict
from itertools import takewhile
from rdflib import RDF, Namespace, Graph, Literal, URIRef

# from https://github.com/clemtoy/pptree
has_print_tree = True
try:
    from pptree import print_tree
except ImportError as e:
    has_print_tree = False

parser = argparse.ArgumentParser(description='Convert a CSV to a Brick space model')
parser.add_argument('--namespace', nargs=2, metavar=('prefix', 'fullnamespace'), action='append', default=[])
parser.add_argument("input_file", metavar='INPUTFILE', help='CSV file to process')
parser.add_argument("output_file", nargs='?', metavar='OUTPUTFILE', help='TTL file to store results')

arguments = parser.parse_args()

input = arguments.input_file
output = arguments.output_file
namespaces = arguments.namespace

prefixes = {
    'brick': 'https://brickschema.org/schema/1.1/Brick#',
    'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
}

for ns in namespaces:
    prefixes[ns[0]] = ns[1]

f = open(input) 
full_data = csv.reader(f)
full_header = next(full_data)

header = [h for h in takewhile(lambda x: x !='', full_header)]
extra_header = full_header[len(header)+1:]

rel_header = [h for h in takewhile(lambda x: x !='', extra_header)]
literal_header = extra_header[len(rel_header)+1:]

def firstEntry(row):
    return next((i for i, x in enumerate(row) if x), None)

# grab the full dataset don't mess around with file iterators
# also filter out blank lines. (TODO: keep them as a reset?)
# FIXME - this got a little too agressive in filtering out blank rows
#full_data = [d for d in full_data if firstEntry(d)]
full_data = [d for d in full_data]

data = [d[:len(header)] for d in full_data]
rel_data = [d[len(header)+1:len(header)+1+len(rel_header)] for d in full_data]
literal_data = [d[len(header)+1+len(rel_header)+1:] for d in full_data]

class Node:
  def __init__(self, id, type):
    self.id = id
    self.type = type
    self.rels = []
    self.literals = []
    self.children = []

  def __repr__(self):
    return '{}({})({}) '.format(self.id,self.rels,self.literals)

  def __str__(self):
    return '{}({})({})'.format(self.id,self.rels,self.literals)
    #return 'id {} type {} children {}'.format(self.id, self.type, self.children)

# test code ignore
tree = Node('jci', 'brick:Core')
jci507 = Node('507', 'brick:Site')
b1 = Node('B1', 'brick:Building')
floor1 = Node('F1', 'brick:Floor')
zone1 = Node('Z1', 'brick:Zone')
r1 = Node('R1', 'brick:Room')
r2 = Node('R2', 'brick:Room')
floor2  = Node('F2', 'brick:Floor')
r3 = Node('R3', 'brick:Room')

floor2.children.append(r3)
floor1.children.append(r1)
floor1.children.append(r2)
b1.children.append(floor1)
b1.children.append(floor2)
jci507.children.append(b1)

#print(jci507)
#exit()


parents = []
for i in range(len(data)):
  parents.append([None for i in range(len(header))])

# solve first row for parent recurrence relationship
i = 0
line = data[0]

#leftmost = firstEntry(line)
#rightmost = len(line) - firstEntry(reversed(line)) - 1
#print('{}: Leftmost: {} Rightmost: {}'.format(i+2, leftmost, rightmost))
nextparent = None
for col, value in enumerate(line):
    parents[i][col] = nextparent
    if value != '':
      nextparent = (i,col)

# solve remaining parents. Our parent is either the cell to the left of us
# in the the same row, or if we're the only thing on this row, it's the parent
# of the cell above us
for row in range(1,len(data)):
    leftmost = None
    if data[row][0] != '':
        leftmost = (row, 0)
    for col, value in enumerate(data[row][1:], 1):
        #print("Considering {},{} ({})".format(row, col, value))
        if leftmost is None:
            parents[row][col] = parents[row-1][col]
        else:
            parents[row][col] = leftmost
        if value != '':
            leftmost = (row, col) 

#for i, r in enumerate(parents):
#    print("{}: {}".format(i, r))

# Now we know what the parent of every cell should be
# so build a tree over the non-blank cells
tree = Node('Overall', 'brick:Core')

childcache = {}

for row, line in enumerate(data):
    rightmost = len(line) - firstEntry(reversed(line)) - 1
    for col, value in enumerate(line):
        if value != '':
            node = Node(value, header[col])
            if col == rightmost:
                node.rels = [y for y in filter(lambda x: x[1] != '', zip(rel_header, rel_data[row]))]
                node.literals = [y for y in filter(lambda x: x[1] != '', zip(literal_header, literal_data[row]))]

            childcache[(row, col)] = node
            if parents[row][col] is None:
                tree.children.append(node)
            else:
                childcache[parents[row][col]].children.append(node)

#print(tree.id)
#print(tree.type)
#print(len(tree.children))

if has_print_tree:
    for t in tree.children:
        print_tree(t, childattr='children')

g = Graph()
BRICK = Namespace('https://brickschema.org/schema/1.1/Brick#')
for pfx, ns in prefixes.items():
    g.bind(pfx, ns)

# stolen from https://github.com/gtfierro/brick-builder/blob/master/make.py
def apply_prefix(uri):
    for pfx, ns in prefixes.items():
        if uri.startswith(f'{pfx}:'):
            return URIRef(uri.replace(f'{pfx}:', ns))
    return URIRef(uri)

def build_rdf_tree(tree):
   global g
   g.add((apply_prefix(tree.id), RDF.type, apply_prefix(tree.type)))
   for rel in tree.rels:
       g.add((apply_prefix(tree.id), apply_prefix(rel[0]), apply_prefix(rel[1])))
   for lit in tree.literals:
       g.add((apply_prefix(tree.id), apply_prefix(lit[0]), Literal(lit[1])))
   for child in tree.children:
       g.add((apply_prefix(tree.id), BRICK.hasPart, apply_prefix(child.id)))
       build_rdf_tree(child)

for t in tree.children:
    build_rdf_tree(t)

print(g.serialize(format="turtle").decode("utf-8"))
