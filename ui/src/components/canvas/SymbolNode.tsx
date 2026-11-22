// Symbol node of the Graph_View. Shows the mastery of its file, labelled file-level
// (Requirement 15.13).
import { memo } from 'react';
import type { NodeProps } from '@xyflow/react';
import { NodeFrame, type GraphFlowNode } from './FileNode';

function SymbolNodeImpl({ data }: NodeProps<GraphFlowNode>) {
  return <NodeFrame data={data} />;
}

export const SymbolNode = memo(SymbolNodeImpl);
