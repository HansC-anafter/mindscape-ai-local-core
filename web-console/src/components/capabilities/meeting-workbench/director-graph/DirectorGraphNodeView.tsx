import { Handle, Position, type NodeProps, type NodeTypes } from '@xyflow/react';

import { nodeTypePorts, type DirectorGraphFlowNode } from './DirectorGraphCanvasModel';

export function DirectorGraphNodeView({ data, selected }: NodeProps<DirectorGraphFlowNode>) {
  const inputPorts = nodeTypePorts(data.nodeType, 'input');
  const outputPorts = nodeTypePorts(data.nodeType, 'output');
  return (
    <div
      className={`min-h-24 w-56 rounded-md border bg-white px-3 py-2 shadow-sm dark:bg-slate-950 ${
        selected ? 'border-blue-400 ring-2 ring-blue-100 dark:ring-blue-900/40' : 'border-slate-200 dark:border-slate-800'
      }`}
      data-testid={`director-graph-node-${data.graphNode.id}`}
    >
      {inputPorts.map((port, index) => (
        <Handle
          key={port.id}
          id={port.id}
          type="target"
          position={Position.Left}
          style={{ top: `${((index + 1) / (inputPorts.length + 1)) * 100}%` }}
        />
      ))}
      <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">
        {data.nodeType.capability_code || data.nodeType.source}
      </div>
      <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{data.nodeType.label}</div>
      <div className="mt-1 flex items-center justify-between gap-2">
        <div className="truncate font-mono text-[11px] text-slate-500 dark:text-slate-400">{data.graphNode.id}</div>
        {data.runStatus ? (
          <span className="shrink-0 rounded-sm bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600 dark:bg-slate-900 dark:text-slate-300">
            {data.runStatus}
          </span>
        ) : null}
      </div>
      {outputPorts.map((port, index) => (
        <Handle
          key={port.id}
          id={port.id}
          type="source"
          position={Position.Right}
          style={{ top: `${((index + 1) / (outputPorts.length + 1)) * 100}%` }}
        />
      ))}
    </div>
  );
}

export const nodeTypes: NodeTypes = { compositionGraphNode: DirectorGraphNodeView };
