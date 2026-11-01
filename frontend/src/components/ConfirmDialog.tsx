import { type ReactNode, useEffect, useRef } from "react";

export function ConfirmDialog(props: {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (props.open && !dialog.open) dialog.showModal();
    if (!props.open && dialog.open) dialog.close();
  }, [props.open]);

  return (
    <dialog ref={ref} className="dialog" onClose={props.onCancel}>
      <h2>{props.title}</h2>
      <div className="dialog-body">{props.children}</div>
      <div className="dialog-actions">
        <button className="btn" onClick={props.onCancel}>
          Cancel
        </button>
        <button className="btn btn-primary" onClick={props.onConfirm}>
          {props.confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
