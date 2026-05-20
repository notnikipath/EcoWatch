import React from "react";

const levels = [
  { label: "Low", color: "#4fbf8f" },
  { label: "Moderate", color: "#f0b14a" },
  { label: "High", color: "#ef6d4f" },
  { label: "Critical", color: "#bf3f5b" },
];

export function Legend() {
  return (
    <div className="legend">
      <p>Risk level</p>
      <div className="legend-grid">
        {levels.map((level) => (
          <span key={level.label}>
            <i style={{ background: level.color }} />
            {level.label}
          </span>
        ))}
      </div>
    </div>
  );
}
