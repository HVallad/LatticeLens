import { useState, useMemo, useCallback } from 'react';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { Sidebar } from './components/layout/Sidebar';
import { EditPanel } from './components/layout/EditPanel';
import { GraphCanvas } from './components/graph/GraphCanvas';
import { GraphControls } from './components/graph/GraphControls';
import { SearchBar } from './components/search/SearchBar';
import { FilterPanel } from './components/search/FilterPanel';
import { ThemeToggle } from './components/common/ThemeToggle';
import { useTheme } from './hooks/useTheme';
import { useSSE } from './hooks/useSSE';
import {
  useFacts,
  useFact,
  useGraphData,
  useTags,
  useEnums,
  useRoles,
  useRoleContext,
  useCreateFact,
  useUpdateFact,
  useDeprecateFact,
  usePromoteFact,
} from './api/hooks';
import type { FactLayer, FactStatus } from './types/fact';
import type { GraphLayout } from './types/graph';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5000, retry: 1 },
  },
});

function AppInner() {
  const { theme, toggle: toggleTheme } = useTheme();
  const qc = useQueryClient();
  useSSE(qc);

  // State
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeLayer, setActiveLayer] = useState<FactLayer | null>(null);
  const [activeStatuses, setActiveStatuses] = useState<Set<FactStatus>>(
    new Set(['Active', 'Draft', 'Under Review'])
  );
  const [graphLayout, setGraphLayout] = useState<GraphLayout>('force');
  const [editMode, setEditMode] = useState<'create' | 'edit' | null>(null);
  const [editCode, setEditCode] = useState<string | null>(null);
  const [activeRole, setActiveRole] = useState<string | null>(null);

  // Data queries
  const statusParam = [...activeStatuses].join(',');
  const factsQuery = useFacts({
    ...(activeLayer ? { layer: activeLayer } : {}),
    status: statusParam,
  });
  const selectedFactQuery = useFact(selectedCode);
  const graphQuery = useGraphData();
  const tagsQuery = useTags();
  const enumsQuery = useEnums();
  const rolesQuery = useRoles();
  const roleContextQuery = useRoleContext(activeRole);

  // Mutations
  const createMutation = useCreateFact();
  const updateMutation = useUpdateFact();
  const deprecateMutation = useDeprecateFact();
  const promoteMutation = usePromoteFact();

  const facts = factsQuery.data || [];
  const graphData = graphQuery.data || { nodes: [], edges: [] };
  const tags = tagsQuery.data || [];
  const enums = enumsQuery.data;
  const roles = rolesQuery.data || {};
  const roleContext = roleContextQuery.data;

  // Search matching
  const searchMatchingCodes = useMemo(() => {
    if (!searchQuery.trim()) return null;
    const q = searchQuery.toLowerCase();
    const matched = new Set<string>();

    for (const fact of facts) {
      if (
        fact.code.toLowerCase().includes(q) ||
        fact.fact.toLowerCase().includes(q) ||
        fact.tags.some((t) => t.includes(q)) ||
        fact.type.toLowerCase().includes(q) ||
        fact.layer.toLowerCase().includes(q) ||
        fact.projects.some((p) => p.toLowerCase().includes(q)) ||
        fact.owner.toLowerCase().includes(q)
      ) {
        matched.add(fact.code);
      }
    }

    return matched;
  }, [searchQuery, facts]);

  // Role context matching (takes priority over search when active)
  const roleMatchingCodes = useMemo(() => {
    if (!activeRole || !roleContext) return null;
    return new Set(roleContext.codes);
  }, [activeRole, roleContext]);

  // Combined: role overrides search
  const matchingCodes = roleMatchingCodes || searchMatchingCodes;

  const allCodes = useMemo(() => facts.map((f) => f.code), [facts]);

  const handleSelectCode = useCallback((code: string) => {
    setSelectedCode(code || null);
  }, []);

  const handleDoubleClickNode = useCallback(
    (_code: string) => {
      // Future: expand/collapse neighbors via BFS
    },
    []
  );

  const handleStatusToggle = useCallback((status: FactStatus) => {
    setActiveStatuses((prev) => {
      const next = new Set(prev);
      if (next.has(status)) {
        next.delete(status);
      } else {
        next.add(status);
      }
      return next;
    });
  }, []);

  const handlePromote = useCallback(
    (code: string) => {
      const reason = prompt('Reason for promotion:');
      if (reason) {
        promoteMutation.mutate({ code, reason });
      }
    },
    [promoteMutation]
  );

  const handleDeprecate = useCallback(
    (code: string) => {
      const reason = prompt('Reason for deprecation:');
      if (reason) {
        deprecateMutation.mutate({ code, reason });
      }
    },
    [deprecateMutation]
  );

  const handleEdit = useCallback((code: string) => {
    setEditCode(code);
    setEditMode('edit');
  }, []);

  const handleNewFact = useCallback(() => {
    setEditCode(null);
    setEditMode('create');
  }, []);

  const handleSave = useCallback(
    (data: any) => {
      if (editMode === 'create') {
        createMutation.mutate(data, {
          onSuccess: (result: any) => {
            if (!result.error) {
              setEditMode(null);
              setSelectedCode(result.code);
            }
          },
        });
      } else {
        updateMutation.mutate(data, {
          onSuccess: (result: any) => {
            if (!result.error) {
              setEditMode(null);
            }
          },
        });
      }
    },
    [editMode, createMutation, updateMutation]
  );

  const editFact = editCode ? facts.find((f) => f.code === editCode) || null : null;

  return (
    <div className={`app-shell ${editMode ? 'edit-open' : ''}`}>
      {/* Header */}
      <div className="header">
        <div className="header-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5 12 2" />
            <line x1="12" y1="22" x2="12" y2="15.5" />
            <polyline points="22 8.5 12 15.5 2 8.5" />
          </svg>
          LatticeLens
        </div>

        <SearchBar
          value={searchQuery}
          onChange={(q) => {
            setSearchQuery(q);
            if (q.trim()) setActiveRole(null);
          }}
          tags={tags}
          allCodes={allCodes}
        />

        <div className="header-actions">
          {Object.keys(roles).length > 0 && (
            <select
              className="role-select"
              value={activeRole || ''}
              onChange={(e) => {
                const val = e.target.value || null;
                setActiveRole(val);
                if (val) setSearchQuery('');
              }}
            >
              <option value="">Role view...</option>
              {Object.entries(roles).map(([key, role]) => (
                <option key={key} value={key}>
                  {role.name}
                </option>
              ))}
            </select>
          )}
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
        </div>
      </div>

      {/* Sidebar */}
      <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {enums && (
          <FilterPanel
            layers={enums.layers}
            activeLayer={activeLayer}
            onLayerChange={setActiveLayer}
            statusFilters={enums.statuses}
            activeStatuses={activeStatuses}
            onStatusToggle={handleStatusToggle}
          />
        )}
        {activeRole && roleContext && (
          <div className="role-info-bar">
            <span>
              <strong>{roles[activeRole]?.name}</strong>: {roleContext.facts_loaded} facts, ~{roleContext.total_tokens} tokens
            </span>
            <button className="btn-sm" style={{ marginLeft: 'auto', padding: '2px 6px', fontSize: 10, border: '1px solid var(--border)', borderRadius: 4, background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer' }} onClick={() => setActiveRole(null)}>Clear</button>
          </div>
        )}
        <Sidebar
          facts={facts}
          selectedCode={selectedCode}
          selectedFact={selectedFactQuery.data || null}
          matchingCodes={matchingCodes}
          onSelect={handleSelectCode}
          onPromote={handlePromote}
          onDeprecate={handleDeprecate}
          onEdit={handleEdit}
          onNewFact={handleNewFact}
        />
      </div>

      {/* Graph Canvas */}
      <div style={{ position: 'relative', overflow: 'hidden' }}>
        <GraphControls
          layout={graphLayout}
          onToggleLayout={() =>
            setGraphLayout((l) => (l === 'force' ? 'layered' : 'force'))
          }
        />
        <GraphCanvas
          data={graphData}
          selectedCode={selectedCode}
          matchingCodes={matchingCodes}
          layout={graphLayout}
          onSelectNode={handleSelectCode}
          onDoubleClickNode={handleDoubleClickNode}
        />
      </div>

      {/* Edit Panel */}
      {editMode && enums && (
        <EditPanel
          mode={editMode}
          fact={editFact}
          enums={enums}
          onSave={handleSave}
          onClose={() => setEditMode(null)}
        />
      )}
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppInner />
    </QueryClientProvider>
  );
}
