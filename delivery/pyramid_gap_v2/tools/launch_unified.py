"""Compatibility entry; fresh delivery semantics live in tools.delivery."""
from tools.delivery import GRAPH, fresh_graph as _fresh_graph, main, prepare, run_prepared, validate

if __name__ == '__main__':
    main()
