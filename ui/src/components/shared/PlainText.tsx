// Renders backend text as a text node. Never interprets HTML or Markdown
// (Requirement 29.10).

import type { ElementType } from 'react';

export interface PlainTextProps {
  text: string;
  as?: ElementType;
  className?: string;
  title?: string;
}

export function PlainText({ text, as, className, title }: PlainTextProps) {
  const Tag: ElementType = as ?? 'span';
  return (
    <Tag className={className} style={{ whiteSpace: 'pre-wrap' }} title={title}>
      {text}
    </Tag>
  );
}
