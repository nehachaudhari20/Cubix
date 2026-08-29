"use client";
import { useEffect, useRef, useState } from "react";

/**
 * Animated counter that increments from startVal to endVal.
 * Supports continuous auto-increment mode for live-feeling KPI growth.
 */
export default function AnimatedCounter({
  startVal,
  endVal,
  prefix = "",
  suffix = "",
  duration = 2000,
  decimals = 0,
  storageKey,
  increment = 0,
  autoIncrement = false,
  incrementInterval = 3000,
  incrementBy = 1,
  capValue = 0,
}: {
  startVal: number;
  endVal: number;
  prefix?: string;
  suffix?: string;
  duration?: number;
  decimals?: number;
  storageKey?: string;
  increment?: number;
  autoIncrement?: boolean;
  incrementInterval?: number;
  incrementBy?: number;
  capValue?: number;
}) {
  const [current, setCurrent] = useState(startVal);
  const [animating, setAnimating] = useState({ from: startVal, to: endVal, key: 0 });
  const mountedRef = useRef(true);

  // Resolve initial value from localStorage + increment
  useEffect(() => {
    let finalVal = endVal;
    if (storageKey) {
      const stored = localStorage.getItem(storageKey);
      if (stored) {
        finalVal = Number(stored) + increment;
      }
      if (!autoIncrement) {
        localStorage.setItem(storageKey, String(finalVal));
      }
    }
    setAnimating({ from: startVal, to: finalVal, key: 0 });
  }, [endVal, storageKey, increment, autoIncrement, startVal]);

  // Animate from → to, then stop
  useEffect(() => {
    mountedRef.current = true;
    const { from, to } = animating;
    const startTime = Date.now();
    const timer = setInterval(() => {
      if (!mountedRef.current) return;
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setCurrent(from + (to - from) * eased);
      if (progress >= 1) {
        setCurrent(to);
        clearInterval(timer);
      }
    }, 16);
    return () => {
      mountedRef.current = false;
      clearInterval(timer);
    };
  }, [animating, duration]);

  // Auto-increment: bump target slowly, animate from current → new target
  useEffect(() => {
    if (!autoIncrement) return;
    const timer = setInterval(() => {
      setCurrent((prev) => {
        const next = capValue > 0 ? Math.min(prev + incrementBy, capValue) : prev + incrementBy;
        if (storageKey) {
          localStorage.setItem(storageKey, String(next));
        }
        // Kick a smooth animation from prev → next
        setAnimating({ from: prev, to: next, key: Date.now() });
        return next;
      });
    }, incrementInterval);
    return () => clearInterval(timer);
  }, [autoIncrement, incrementInterval, incrementBy, capValue, storageKey]);

  const formatted =
    decimals > 0
      ? current.toFixed(decimals)
      : Math.round(current).toLocaleString();

  return (
    <span>
      {prefix}
      {formatted}
      {suffix}
    </span>
  );
}
