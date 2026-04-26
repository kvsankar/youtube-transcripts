import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Two-pane horizontal layout with a draggable divider.
 *
 * - `initialLeftPct` controls the starting split (0..100).
 * - The user can drag the divider to any position from 0 to 100,
 *   so either pane can be collapsed entirely.
 * - Stores the latest position in localStorage under `storageKey` so it
 *   persists across reloads.
 */
export function Splitter({
  left,
  right,
  initialLeftPct = 60,
  storageKey,
}: {
  left: ReactNode;
  right: ReactNode;
  initialLeftPct?: number;
  storageKey?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);

  const [leftPct, setLeftPct] = useState<number>(() => {
    if (storageKey) {
      const raw = localStorage.getItem(storageKey);
      if (raw != null) {
        const parsed = parseFloat(raw);
        if (!Number.isNaN(parsed)) return clamp(parsed, 0, 100);
      }
    }
    return initialLeftPct;
  });

  useEffect(() => {
    if (storageKey) localStorage.setItem(storageKey, String(leftPct));
  }, [leftPct, storageKey]);

  const onMove = useCallback((clientX: number) => {
    const el = containerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const pct = ((clientX - rect.left) / rect.width) * 100;
    setLeftPct(clamp(pct, 0, 100));
  }, []);

  useEffect(() => {
    function onMouseMove(e: MouseEvent) {
      if (!draggingRef.current) return;
      e.preventDefault();
      onMove(e.clientX);
    }
    function onMouseUp() {
      if (!draggingRef.current) return;
      draggingRef.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [onMove]);

  const startDrag = (e: React.MouseEvent) => {
    e.preventDefault();
    draggingRef.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  return (
    <div className="splitter" ref={containerRef}>
      <div className="splitter-pane" style={{ width: `${leftPct}%` }}>
        {left}
      </div>
      <div
        className="splitter-divider"
        onMouseDown={startDrag}
        title="Drag to resize"
        role="separator"
        aria-orientation="vertical"
      />
      <div
        className="splitter-pane splitter-pane-right"
        style={{ width: `calc(${100 - leftPct}% - 6px)` }}
      >
        {right}
      </div>
    </div>
  );
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}
