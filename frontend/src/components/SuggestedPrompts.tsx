"use client";

interface SuggestedPromptsProps {
  onSelect: (prompt: string) => void;
  disabled?: boolean;
}

const PROMPTS = [
  "Show me luxury villas for sale in Dubai",
  "Find 3-bedroom apartments in Riyadh under SAR 2M",
  "What are the most expensive properties from DarGlobal?",
  "List sea-view properties in Jeddah",
  "Compare Wasalt and DarGlobal listings",
  "Show branded residences like Lamborghini or Aston Martin",
];

export default function SuggestedPrompts({ onSelect, disabled }: SuggestedPromptsProps) {
  return (
    <div className="flex flex-wrap gap-2 justify-center">
      {PROMPTS.map((prompt) => (
        <button
          key={prompt}
          onClick={() => onSelect(prompt)}
          disabled={disabled}
          className="text-sm px-3 py-2 rounded-full border border-[#c9a84c]/40 text-[#c9a84c] 
                     hover:bg-[#c9a84c]/10 hover:border-[#c9a84c] transition-all duration-200
                     disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
        >
          {prompt}
        </button>
      ))}
    </div>
  );
}
