"""VeriAgent engine: perceive → decide → record → execute → verify.

The one invariant this engine enforces (and the reason it exists):
**a trade cannot execute before its decision credential exists.**

Chain-side enforcement lives in DecisionRecorder.sol (bindTx requires record);
engine-side enforcement lives in agent.VeriAgent._assert_order().
"""

__version__ = "0.1.0"
