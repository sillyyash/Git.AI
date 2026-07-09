from core.indexer import build_index
from core.repository import scan_repository
from core.graph import build_graph
from core.relationship import RelationshipBuilder
from core import intelligence

repo = scan_repository('repos/website')
index = build_index(repo)
graph = build_graph(index)
relationships = RelationshipBuilder(index).build()

print('Architecture:', intelligence.detect_architecture(index, graph, relationships))
print('Frameworks:', intelligence.detect_frameworks(index, graph, relationships))
print('Routes:', intelligence.detect_routes(index, graph, relationships)[:5])
print('Components:', intelligence.detect_components(index, graph, relationships)[:5])
print('Entry points:', intelligence.detect_entry_points(index, graph, relationships))
print('Configuration:', intelligence.detect_configuration(index, graph, relationships)[:5])
print('Build system:', intelligence.detect_build_system(index, graph, relationships))
print('Package manager:', intelligence.detect_package_manager(index, graph, relationships))
print('Testing:', intelligence.detect_testing_framework(index, graph, relationships))
print('Deployment:', intelligence.detect_deployment(index, graph, relationships))
