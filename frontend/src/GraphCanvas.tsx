import { useMemo } from "react";
import type { VisualGraphData, VisualGraphNode } from "./types";

interface GraphCanvasProps {
  graph: VisualGraphData;
  selectedNodeId: string | null;
  onSelectNode: (node: VisualGraphNode) => void;
}

type PositionedNode = VisualGraphNode & { x: number; y: number; radius: number };

const width = 920;
const height = 540;
const palette = ["#3978c5", "#3d9661", "#bd8121", "#7655c7", "#b9527c", "#248a91", "#526cc4"];

export function GraphCanvas({ graph, selectedNodeId, onSelectNode }: GraphCanvasProps) {
  const positioned = useMemo(() => layoutNodes(graph), [graph]);
  const byId = new Map(positioned.map((node) => [node.id, node]));
  const neighborIds = new Set<string>();
  graph.lines.forEach((line) => {
    if (line.from === selectedNodeId) neighborIds.add(line.to);
    if (line.to === selectedNodeId) neighborIds.add(line.from);
  });

  return (
    <div className="kg-canvas-shell">
      <svg className="kg-canvas" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="知识图谱可视化">
        <rect className="kg-canvas-bg" x="0" y="0" width={width} height={height} rx="10" />
        <g>
          {graph.lines.map((line, index) => {
            const source = byId.get(line.from);
            const target = byId.get(line.to);
            if (!source || !target) return null;
            const connected = selectedNodeId && (line.from === selectedNodeId || line.to === selectedNodeId);
            return (
              <g className={connected ? "kg-line connected" : "kg-line"} key={line.id ?? `${line.from}-${line.to}-${index}`}>
                <line x1={source.x} y1={source.y} x2={target.x} y2={target.y} />
                <text x={(source.x + target.x) / 2} y={(source.y + target.y) / 2}>
                  {line.text}
                </text>
              </g>
            );
          })}
        </g>
        <g>
          {positioned.map((node) => {
            const selected = node.id === selectedNodeId;
            const neighbor = neighborIds.has(node.id);
            const color = nodeColor(node);
            return (
              <g
                className={`kg-node ${selected ? "selected" : ""} ${neighbor ? "neighbor" : ""}`}
                key={node.id}
                onClick={() => onSelectNode(node)}
                role="button"
                tabIndex={0}
              >
                <circle cx={node.x} cy={node.y} r={node.radius} fill={color.fill} stroke={color.stroke} />
                <text className="kg-node-type" x={node.x} y={node.y - 5}>
                  {node.type === "CommunityNode" ? "社区" : String(node.data.point_type ?? "知识点")}
                </text>
                <text className="kg-node-label" x={node.x} y={node.y + 13}>
                  {truncate(node.text, 14)}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}

function layoutNodes(graph: VisualGraphData): PositionedNode[] {
  const nodes = graph.nodes;
  if (!nodes.length) return [];
  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.min(220, Math.max(120, nodes.length * 18));
  return nodes.map((node, index) => {
    const angle = -Math.PI / 2 + (Math.PI * 2 * index) / nodes.length;
    const nodeRadius = node.type === "CommunityNode" ? 46 : 36;
    return {
      ...node,
      x: nodes.length === 1 ? centerX : centerX + Math.cos(angle) * radius,
      y: nodes.length === 1 ? centerY : centerY + Math.sin(angle) * radius,
      radius: nodeRadius,
    };
  });
}

function nodeColor(node: VisualGraphNode) {
  if (node.type === "CommunityNode") {
    const index = hash(node.id) % palette.length;
    return { fill: "#f8fbff", stroke: palette[index] };
  }
  const pointType = String(node.data.point_type ?? "");
  if (pointType === "source") return { fill: "#eef8fb", stroke: "#248a91" };
  if (pointType === "tag") return { fill: "#fff6dd", stroke: "#bd8121" };
  if (pointType === "category") return { fill: "#f3edff", stroke: "#7655c7" };
  return { fill: "#eef8f0", stroke: "#3d9661" };
}

function truncate(value: string, max: number) {
  return value.length > max ? `${value.slice(0, max - 1)}...` : value;
}

function hash(value: string) {
  let result = 0;
  for (const char of value) result = (result * 31 + char.charCodeAt(0)) | 0;
  return Math.abs(result);
}
