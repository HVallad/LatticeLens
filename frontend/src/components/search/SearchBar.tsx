import { useState, useRef, useEffect } from 'react';
import type { TagEntry } from '../../types/fact';

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  tags?: TagEntry[];
  allCodes?: string[];
}

export function SearchBar({ value, onChange, tags, allCodes }: SearchBarProps) {
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!value.trim()) {
      setSuggestions([]);
      return;
    }

    const q = value.toLowerCase();
    const results: string[] = [];

    // Match codes
    if (allCodes) {
      for (const code of allCodes) {
        if (code.toLowerCase().includes(q) && results.length < 8) {
          results.push(code);
        }
      }
    }

    // Match tags
    if (tags) {
      for (const t of tags) {
        if (t.tag.includes(q) && results.length < 12) {
          results.push(`tag:${t.tag}`);
        }
      }
    }

    setSuggestions(results);
  }, [value, tags, allCodes]);

  return (
    <div className="search-container" style={{ position: 'relative' }}>
      <input
        ref={inputRef}
        className="search-input"
        type="text"
        placeholder="Search facts, tags, codes..."
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setShowSuggestions(true)}
        onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
      />
      {showSuggestions && suggestions.length > 0 && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            marginTop: 4,
            zIndex: 100,
            maxHeight: 200,
            overflowY: 'auto',
            boxShadow: 'var(--shadow-lg)',
          }}
        >
          {suggestions.map((s) => (
            <div
              key={s}
              style={{
                padding: '6px 12px',
                fontSize: 13,
                cursor: 'pointer',
                fontFamily: "'SF Mono', 'Consolas', monospace",
              }}
              onMouseDown={() => {
                onChange(s);
                setShowSuggestions(false);
              }}
            >
              {s}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
