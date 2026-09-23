from .state import ImpactState
from .nodes import *
try:from langgraph.graph import StateGraph,END
except ImportError:StateGraph=None
class Local:
 def invoke(self,s):
  s=init(s)
  if s.get("event_type")=="merge":return merge(s)
  for n in (diff,dependencies,consumers,schemas,testmap,severity,actions):s=n(s)
  return s
def build():
 if StateGraph is None:return Local()
 g=StateGraph(ImpactState)
 for name,node in [("init",init),("diff",diff),("dependencies",dependencies),("consumers",consumers),("schemas",schemas),("tests",testmap),("severity",severity),("actions",actions),("merge",merge)]:g.add_node(name,node)
 g.set_entry_point("init");g.add_conditional_edges("init",lambda s:"merge" if s.get("event_type")=="merge" else "diff",{"merge":"merge","diff":"diff"})
 for a,b in [("diff","dependencies"),("dependencies","consumers"),("consumers","schemas"),("schemas","tests"),("tests","severity"),("severity","actions")]:g.add_edge(a,b)
 g.add_edge("actions",END);g.add_edge("merge",END);return g.compile()
agent=build()
