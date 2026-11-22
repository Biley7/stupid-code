// Circular dependency edge: dashed crimson stroke, text marker CIRCULAR (Requirement 15.9).
// The pulse is the static `edge-circular` class in styles/index.css (Autopsy only).
import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath, type Edge, type EdgeProps } from '@xyflow/react';
import { memo } from 'react';

export type CircularEdgeData = { dimmed: boolean };
export type CircularFlowEdge = Edge<CircularEdgeData, 'circular'>;

function CircularEdgeImpl({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  data,
}: EdgeProps<CircularFlowEdge>) {
  const [path, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });
  const dimmed = data?.dimmed === true;
  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        className="edge-circular"
        style={{
          stroke: 'var(--color-crimson)',
          strokeWidth: 1.5,
          strokeDasharray: '6 4',
          opacity: dimmed ? 0.35 : 1,
        }}
      />
      <EdgeLabelRenderer>
        <span
          data-edge-marker="CIRCULAR"
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            opacity: dimmed ? 0.35 : 1,
          }}
          className="pointer-events-none border border-crimson bg-obsidian px-1 font-mono text-[10px] text-signal"
        >
          CIRCULAR
        </span>
      </EdgeLabelRenderer>
    </>
  );
}

export const CircularEdge = memo(CircularEdgeImpl);
