import { useEffect, useRef, useCallback, useState } from 'react';
import * as d3 from 'd3';
import type { GraphData, GraphNode, GraphEdge, GraphLayout } from '../../types/graph';
import { STATUS_COLORS, EDGE_STYLES } from '../../utils/colors';
import type { FactStatus, EdgeType } from '../../types/fact';

interface GraphCanvasProps {
  data: GraphData;
  selectedCode: string | null;
  matchingCodes: Set<string> | null;
  layout: GraphLayout;
  onSelectNode: (code: string) => void;
  onDoubleClickNode: (code: string) => void;
}

const NODE_RADIUS = 20;


export function GraphCanvas({
  data,
  selectedCode,
  matchingCodes,
  layout,
  onSelectNode,
  onDoubleClickNode,
}: GraphCanvasProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const simulationRef = useRef<d3.Simulation<GraphNode, GraphEdge> | null>(null);
  const containerRef = useRef<d3.Selection<SVGGElement, unknown, null, undefined> | null>(null);
  const [tooltip, setTooltip] = useState<{
    x: number;
    y: number;
    node: GraphNode;
  } | null>(null);

  // Store latest callbacks in refs so the structural render doesn't depend on them
  const onSelectNodeRef = useRef(onSelectNode);
  onSelectNodeRef.current = onSelectNode;
  const onDoubleClickNodeRef = useRef(onDoubleClickNode);
  onDoubleClickNodeRef.current = onDoubleClickNode;

  // Structural render — only rebuilds when data or layout changes
  const renderGraph = useCallback(() => {
    if (!svgRef.current || !data.nodes.length) return;

    const svg = d3.select(svgRef.current);
    const width = svgRef.current.clientWidth;
    const height = svgRef.current.clientHeight;

    // Clear previous
    svg.selectAll('*').remove();
    simulationRef.current?.stop();

    // Create defs for arrowheads
    const defs = svg.append('defs');
    Object.entries(EDGE_STYLES).forEach(([rel, style]) => {
      defs
        .append('marker')
        .attr('id', `arrow-${rel}`)
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 28)
        .attr('refY', 0)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', style.color);
    });

    // Clone data to avoid mutation
    const nodes: GraphNode[] = data.nodes.map((n) => ({ ...n }));
    const edges: GraphEdge[] = data.edges.map((e) => ({ ...e }));

    // Set up container with zoom
    const g = svg.append('g');
    containerRef.current = g;
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
      });
    svg.call(zoom);

    // Initial zoom to fit
    svg.call(zoom.transform, d3.zoomIdentity.translate(width / 2, height / 2).scale(0.8));

    // Draw edges
    g.selectAll<SVGLineElement, GraphEdge>('.edge')
      .data(edges, (d) => `${(d.source as GraphNode).code || d.source}-${(d.target as GraphNode).code || d.target}`)
      .join('line')
      .attr('class', 'edge')
      .attr('stroke-width', 1.5)
      .attr('stroke', (d) => EDGE_STYLES[d.rel as EdgeType]?.color || '#999')
      .attr('stroke-dasharray', (d) => EDGE_STYLES[d.rel as EdgeType]?.dash || '')
      .attr('marker-end', (d) => `url(#arrow-${d.rel})`)
      .attr('opacity', 0.6);

    // Draw nodes
    const nodeGroups = g.selectAll<SVGGElement, GraphNode>('.node')
      .data(nodes, (d) => d.code)
      .join('g')
      .attr('class', 'node')
      .style('cursor', 'pointer');

    // Add shapes per layer
    nodeGroups.each(function (d) {
      const group = d3.select(this);
      if (d.layer === 'WHY') {
        group
          .append('circle')
          .attr('r', NODE_RADIUS)
          .attr('stroke', 'transparent')
          .attr('stroke-width', 2);
      } else if (d.layer === 'GUARDRAILS') {
        group
          .append('polygon')
          .attr(
            'points',
            `0,${-NODE_RADIUS} ${NODE_RADIUS},0 0,${NODE_RADIUS} ${-NODE_RADIUS},0`
          )
          .attr('stroke', 'transparent')
          .attr('stroke-width', 2);
      } else {
        group
          .append('rect')
          .attr('x', -NODE_RADIUS)
          .attr('y', -NODE_RADIUS)
          .attr('width', NODE_RADIUS * 2)
          .attr('height', NODE_RADIUS * 2)
          .attr('rx', 3)
          .attr('stroke', 'transparent')
          .attr('stroke-width', 2);
      }

      // Label
      group
        .append('text')
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'central')
        .attr('font-size', 9)
        .attr('font-weight', 600)
        .attr('fill', '#fff')
        .attr('pointer-events', 'none')
        .text(d.code);
    });

    // Fill colors
    nodeGroups.select('circle, polygon, rect').attr('fill', (d) => STATUS_COLORS[d.status as FactStatus]);

    // Events — use refs so we don't rebind on every callback change
    nodeGroups
      .on('click', (event, d) => {
        event.stopPropagation();
        onSelectNodeRef.current(d.code);
      })
      .on('dblclick', (event, d) => {
        event.stopPropagation();
        onDoubleClickNodeRef.current(d.code);
      })
      .on('mouseenter', (event, d) => {
        const rect = svgRef.current!.getBoundingClientRect();
        setTooltip({
          x: event.clientX - rect.left + 10,
          y: event.clientY - rect.top - 10,
          node: d,
        });
      })
      .on('mouseleave', () => setTooltip(null));

    // Position update function (used by simulation tick and layered layout)
    function updatePositions() {
      g.selectAll<SVGLineElement, GraphEdge>('.edge')
        .attr('x1', (d) => (d.source as GraphNode).x || 0)
        .attr('y1', (d) => (d.source as GraphNode).y || 0)
        .attr('x2', (d) => (d.target as GraphNode).x || 0)
        .attr('y2', (d) => (d.target as GraphNode).y || 0);

      g.selectAll<SVGGElement, GraphNode>('.node')
        .attr('transform', (d) => `translate(${d.x || 0},${d.y || 0})`);
    }

    // Layout
    if (layout === 'force') {
      const simulation = d3
        .forceSimulation<GraphNode>(nodes)
        .force(
          'link',
          d3
            .forceLink<GraphNode, GraphEdge>(edges)
            .id((d) => d.code)
            .distance(120)
        )
        .force('charge', d3.forceManyBody().strength(-300))
        .force('center', d3.forceCenter(0, 0))
        .force('collide', d3.forceCollide(NODE_RADIUS + 10));

      simulationRef.current = simulation;
      simulation.on('tick', updatePositions);

      // Drag
      nodeGroups.call(
        d3
          .drag<SVGGElement, GraphNode>()
          .on('start', (event, d) => {
            if (!event.active) simulationRef.current?.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on('drag', (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on('end', (event, d) => {
            if (!event.active) simulationRef.current?.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          })
      );
    } else {
      // Layered layout
      const layerY: Record<string, number> = { WHY: -200, GUARDRAILS: 0, HOW: 200 };
      const layerGroups: Record<string, GraphNode[]> = { WHY: [], GUARDRAILS: [], HOW: [] };

      nodes.forEach((n) => {
        layerGroups[n.layer]?.push(n);
      });

      Object.entries(layerGroups).forEach(([layer, layerNodes]) => {
        const y = layerY[layer] || 0;
        const spacing = Math.max(80, (width * 0.6) / Math.max(layerNodes.length, 1));
        layerNodes.forEach((n, i) => {
          n.x = (i - (layerNodes.length - 1) / 2) * spacing;
          n.y = y;
        });
      });

      updatePositions();

      // Layer labels
      const layerLabels = [
        { name: 'WHY', y: -200 },
        { name: 'GUARDRAILS', y: 0 },
        { name: 'HOW', y: 200 },
      ];
      g.selectAll('.layer-label')
        .data(layerLabels)
        .join('text')
        .attr('class', 'layer-label')
        .attr('x', -width * 0.35)
        .attr('y', (d) => d.y)
        .attr('text-anchor', 'end')
        .attr('dominant-baseline', 'middle')
        .attr('fill', 'var(--text-muted)')
        .attr('font-size', 12)
        .attr('font-weight', 600)
        .text((d) => d.name);
    }

    // Click on background to deselect
    svg.on('click', () => onSelectNodeRef.current(''));
  }, [data, layout]);

  // Lightweight visual update — only changes opacity and selection ring
  useEffect(() => {
    const g = containerRef.current;
    if (!g) return;

    // Update node opacity + selection ring
    g.selectAll<SVGGElement, GraphNode>('.node')
      .attr('opacity', (d) => {
        if (!matchingCodes) return 1;
        return matchingCodes.has(d.code) ? 1 : 0.2;
      })
      .select('circle, polygon, rect')
      .attr('stroke', (d) => (d.code === selectedCode ? '#fff' : 'transparent'))
      .attr('stroke-width', (d) => (d.code === selectedCode ? 3 : 2));

    // Update edge opacity
    g.selectAll<SVGLineElement, GraphEdge>('.edge')
      .attr('opacity', (d) => {
        if (!matchingCodes) return 0.6;
        const src = (d.source as GraphNode).code || (d.source as string);
        const tgt = (d.target as GraphNode).code || (d.target as string);
        return matchingCodes.has(src) || matchingCodes.has(tgt) ? 0.6 : 0.1;
      });
  }, [matchingCodes, selectedCode]);

  useEffect(() => {
    renderGraph();
    return () => {
      simulationRef.current?.stop();
    };
  }, [renderGraph]);

  // Re-render on resize
  useEffect(() => {
    const handleResize = () => renderGraph();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [renderGraph]);

  return (
    <div className="canvas">
      <svg ref={svgRef} />
      {tooltip && (
        <div className="tooltip" style={{ left: tooltip.x, top: tooltip.y }}>
          <div className="tooltip-code">{tooltip.node.code}</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
            {tooltip.node.type} | {tooltip.node.status}
          </div>
          <div className="tooltip-text">{tooltip.node.fact}</div>
        </div>
      )}
    </div>
  );
}
