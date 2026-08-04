import React, { useEffect, useRef } from 'react';
import { AlertTriangle, HelpCircle, X } from 'lucide-react';

export type ConfirmDialogProps = {
  open: boolean;
  title?: string;
  message?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  open,
  title = 'Confirm action',
  message = 'Are you sure you want to continue?',
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  danger = false,
  onConfirm,
  onCancel,
}) => {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);

  // Focus the cancel button by default (safer default for destructive actions).
  useEffect(() => {
    if (open) {
      cancelRef.current?.focus();
    }
  }, [open]);

  // Keyboard: Escape → cancel, Enter → confirm.
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); onCancel(); }
      if (e.key === 'Enter')  { e.preventDefault(); onConfirm(); }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onConfirm, onCancel]);

  if (!open) return null;

  const Icon = danger ? AlertTriangle : HelpCircle;

  return (
    // Backdrop — click outside cancels.
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
      aria-describedby="confirm-dialog-message"
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
    >
      {/* Dimmed backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onCancel}
        aria-hidden="true"
      />

      {/* Panel */}
      <div className="relative w-full max-w-md rounded-xl border border-gray-200 bg-white shadow-xl dark:border-gray-700 dark:bg-gray-900">
        {/* Close button */}
        <button
          type="button"
          onClick={onCancel}
          className="absolute right-3 top-3 rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-200"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>

        {/* Content */}
        <div className="flex gap-4 p-6">
          <div
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${
              danger
                ? 'bg-red-100 dark:bg-red-900/40'
                : 'bg-blue-100 dark:bg-blue-900/40'
            }`}
          >
            <Icon
              className={`h-5 w-5 ${
                danger ? 'text-red-600 dark:text-red-400' : 'text-blue-600 dark:text-blue-400'
              }`}
            />
          </div>

          <div className="flex-1 pt-0.5">
            <h3
              id="confirm-dialog-title"
              className="text-base font-semibold text-gray-900 dark:text-gray-100"
            >
              {title}
            </h3>
            <p
              id="confirm-dialog-message"
              className="mt-1.5 text-sm text-gray-600 dark:text-gray-400"
            >
              {message}
            </p>
          </div>
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-2 border-t border-gray-100 px-6 py-4 dark:border-gray-800">
          <button
            ref={cancelRef}
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-1 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={onConfirm}
            className={`rounded-lg px-4 py-2 text-sm font-medium text-white focus:outline-none focus:ring-2 focus:ring-offset-1 ${
              danger
                ? 'bg-red-600 hover:bg-red-700 focus:ring-red-500 dark:bg-red-700 dark:hover:bg-red-600'
                : 'bg-brand-600 hover:bg-brand-700 focus:ring-brand-500'
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
};
