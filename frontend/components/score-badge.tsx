type ScoreBadgeProps = {
  score: number;
};

export function ScoreBadge({ score }: ScoreBadgeProps) {
  return <span className="score-badge">Priority {score}</span>;
}
