"use client";

interface ScoreCardProps {
  score: number;
  direction: string;
  confidence: number;
  reason?: string;
  loading?: boolean;
}

function getScoreColor(score: number): string {
  if (score >= 70) return "#00C853";
  if (score >= 40) return "#FFD600";
  return "#FF1744";
}

function getScoreLabel(score: number): string {
  if (score >= 80) return "Strong Buy";
  if (score >= 65) return "Buy";
  if (score >= 55) return "Reinforce";
  if (score >= 45) return "Hold";
  if (score >= 35) return "Reduce";
  if (score >= 20) return "Sell";
  return "Strong Sell";
}

export default function ScoreCard({
  score,
  direction,
  confidence,
  reason,
  loading = false,
}: ScoreCardProps) {
  if (loading) {
    return (
      <div className="card animate-pulse">
        <div className="h-4 bg-surface-hover rounded w-24 mb-4" />
        <div className="mx-auto w-32 h-32 bg-surface-hover rounded-full mb-4" />
        <div className="h-4 bg-surface-hover rounded w-20 mx-auto" />
      </div>
    );
  }

  const color = getScoreColor(score);
  const radius = 60;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const label = getScoreLabel(score);

  return (
    <div className="card">
      <h3 className="text-sm font-medium text-gray-400 mb-4">AI Decision Score</h3>

      <div className="flex flex-col items-center">
        {/* SVG Gauge */}
        <svg width="160" height="160" viewBox="0 0 160 160" className="mb-3" role="img" aria-label={`AI Score: ${score}`}>
          {/* Background circle */}
          <circle
            cx="80"
            cy="80"
            r={radius}
            fill="none"
            stroke="#2a2b3e"
            strokeWidth="10"
          />
          {/* Progress arc */}
          <circle
            cx="80"
            cy="80"
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth="10"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            transform="rotate(-90 80 80)"
            style={{ transition: "stroke-dashoffset 0.8s ease, stroke 0.3s ease" }}
          />
          {/* Center text */}
          <text
            x="80"
            y="74"
            textAnchor="middle"
            fill="white"
            fontSize="28"
            fontWeight="bold"
            fontFamily="Inter, system-ui, sans-serif"
          >
            {score.toFixed(0)}
          </text>
          <text
            x="80"
            y="96"
            textAnchor="middle"
            fill={color}
            fontSize="12"
            fontWeight="500"
            fontFamily="Inter, system-ui, sans-serif"
          >
            / 100
          </text>
        </svg>

        {/* Label */}
        <span
          className="text-lg font-bold mb-1"
          style={{ color }}
        >
          {label}
        </span>

        {/* Direction */}
        <span className="text-sm text-gray-400 capitalize mb-2">
          {direction} · {confidence.toFixed(0)}% confidence
        </span>

        {/* Reason */}
        {reason && (
          <p className="text-xs text-gray-500 text-center mt-2 max-w-[200px] leading-relaxed">
            {reason}
          </p>
        )}
      </div>
    </div>
  );
}
