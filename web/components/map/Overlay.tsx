"use client";

import { useEffect, useId, useRef, type ReactNode, type RefObject } from "react";
import { X } from "@phosphor-icons/react";
import { Button } from "@/components/ui";
import { listenDismiss } from "./dismiss";
import s from "./map.module.css";

/**
 * A popover anchored to its button on desktop and a bottom sheet on phones (same element, the CSS
 * decides). It stays mounted so it can animate out; while closed it is inert and hidden from
 * assistive tech.
 */
export function Overlay({
  open,
  onClose,
  triggerRef,
  title,
  placement,
  children,
  id,
}: {
  open: boolean;
  onClose: () => void;
  triggerRef: RefObject<HTMLElement | null>;
  title: string;
  /** Which way it opens from its button on desktop. */
  placement: "below" | "above";
  children: ReactNode;
  id: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const headingId = useId();

  useEffect(() => {
    const panel = ref.current;
    const trigger = triggerRef.current;
    if (!open || !panel || !trigger) return;
    panel.focus({ preventScroll: true });
    return listenDismiss({ root: document, trigger, panel, onClose });
  }, [open, onClose, triggerRef]);

  return (
    <div
      ref={ref}
      id={id}
      role="dialog"
      aria-labelledby={headingId}
      tabIndex={-1}
      className={s.overlay}
      data-placement={placement}
      data-open={open}
      inert={!open}
      aria-hidden={!open}
    >
      <div className={s.overlayHead}>
        <span className={s.grabber} aria-hidden />
        <h2 id={headingId} className={s.h4}>
          {title}
        </h2>
        <Button
          variant="quiet"
          size="sm"
          icon={<X size={16} />}
          aria-label={`Close ${title.toLowerCase()}`}
          onClick={() => {
            onClose();
            triggerRef.current?.focus({ preventScroll: true });
          }}
        />
      </div>
      <div className={s.overlayBody}>{children}</div>
    </div>
  );
}
