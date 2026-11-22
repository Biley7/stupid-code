// File node of the Graph_View (Requirements 15.10, 15.11, 16.2, 16.6, 16.9, 29.3).
// Mastery is shown as icon plus text; the Shroud is a CSS overlay on top of the text.
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import { memo, type KeyboardEvent } from 'react';
import { MasteryDot } from '../shared/MasteryDot';
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
  // Border colour by role; the Autopsy-only shroud, mastered outline and selected ring
  // classes (styles/index.css) refine this in Autopsy mode.
  const border = blast ? 'border-crimson' : selected || upstream || downstream ? 'border-bone' : 'border-hairline';
  const classes = [
    shroud ? 'node-unaudited' : '',
    mastery.category === 'MASTERED' ? 'node-mastered' : '',
    selected ? 'node-selected' : '',
    'box-border flex flex-col justify-center gap-0.5 overflow-hidden border bg-surface px-2.5',
    border,
    selected ? 'border-2' : '',
  ]
    .filter((c) => c !== '')
    .join(' ');
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
      style={{ width: NODE_WIDTH, height: NODE_HEIGHT, opacity: dimmed ? 0.3 : 1 }}
      className={classes}
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
      <span className="flex items-center gap-1.5 overflow-hidden text-[10px]">
        <MasteryDot presentation={mastery} showLabel />
        {fileLevel ? <span className="text-muted">file-level</span> : null}
        {kind ? <span className="truncate text-muted">{kind}</span> : null}
        {selected ? <span className="font-semibold uppercase tracking-wider text-bone">Selected</span> : null}
        {blast ? <span className="font-semibold uppercase tracking-wider text-signal">Blast</span> : null}
        {upstream ? <span className="font-semibold uppercase tracking-wider text-bone">Upstream</span> : null}
        {downstream ? <span className="font-semibold uppercase tracking-wider text-bone">Downstream</span> : null}
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
