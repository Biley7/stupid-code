// File node of the Graph_View (Requirements 15.10, 15.11, 16.2, 16.6, 16.9, 29.3).
// Mastery is shown as icon plus text; the Shroud is a CSS overlay on top of the text.
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import { memo, type KeyboardEvent } from 'react';
import { MasteryBadge } from '../shared/MasteryBadge';
import { PlainText } from '../shared/PlainText';
import type { MasteryPresentation } from '../../core/mastery';
import { NODE_HEIGHT, NODE_WIDTH } from '../../core/layout';

export type GraphNodeData = {
  id: string;
  label: string;
  /** Symbol kind, present for symbol nodes only. */
  kind?: string;
  mastery: MasteryPresentation;
  /** Symbol nodes show the mastery of their file and say so. */
  fileLevel: boolean;
  shroud: boolean;
  selected: boolean;
  upstream: boolean;
  downstream: boolean;
  blast: boolean;
  dimmed: boolean;
  onSelect: (id: string) => void;
  onClear: () => void;
};

export type GraphFlowNode = Node<GraphNodeData, 'file' | 'symbol'>;

/** Shared markup of both node kinds. */
export function NodeFrame({ data }: { data: GraphNodeData }) {
  const { id, label, kind, mastery, fileLevel, shroud, selected, upstream, downstream, blast, dimmed } =
    data;
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      data.onSelect(id);
    } else if (event.key === 'Escape') {
      data.onClear();
    }
  };
  const border = blast ? 'border-crimson' : selected || upstream || downstream ? 'border-bone' : 'border-hairline';
  return (
    <div
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      aria-label={`${label}, ${mastery.label}${fileLevel ? ' (file-level)' : ''}`}
      data-node-id={id}
      data-mastery={mastery.category}
      data-shroud={shroud ? 'true' : 'false'}
      onKeyDown={onKeyDown}
      style={{ width: NODE_WIDTH, height: NODE_HEIGHT, opacity: dimmed ? 0.35 : 1 }}
      className={`${shroud ? 'node-unaudited ' : ''}box-border flex flex-col justify-center overflow-hidden border bg-surface px-2 ${border} ${
        selected ? 'border-2' : ''
      }`}
    >
      <Handle
        type="target"
        position={Position.Left}
        isConnectable={false}
        className="!h-px !w-px !min-h-0 !min-w-0 !border-0 !bg-hairline"
      />
      <PlainText
        text={label}
        title={id}
        className="block truncate font-mono text-xs text-bone"
      />
      <span className="flex items-center gap-1 overflow-hidden">
        <MasteryBadge presentation={mastery} className="!border-0 !px-0 !py-0 text-[10px]" />
        {fileLevel ? <span className="font-mono text-[10px] text-muted">file-level</span> : null}
        {kind ? <span className="truncate font-mono text-[10px] text-muted">{kind}</span> : null}
        {selected ? <span className="font-mono text-[10px] text-bone">SELECTED</span> : null}
        {blast ? <span className="font-mono text-[10px] text-signal">BLAST</span> : null}
        {upstream ? <span className="font-mono text-[10px] text-bone">UPSTREAM</span> : null}
        {downstream ? <span className="font-mono text-[10px] text-bone">DOWNSTREAM</span> : null}
      </span>
      <Handle
        type="source"
        position={Position.Right}
        isConnectable={false}
        className="!h-px !w-px !min-h-0 !min-w-0 !border-0 !bg-hairline"
      />
    </div>
  );
}

function FileNodeImpl({ data }: NodeProps<GraphFlowNode>) {
  return <NodeFrame data={data} />;
}

export const FileNode = memo(FileNodeImpl);
