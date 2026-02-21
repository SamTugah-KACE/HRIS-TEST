import React, { useState } from 'react';
import { X, CalendarPlus, CheckCircle } from 'lucide-react';

type Props = {
  open: boolean;
  onClose: () => void;
  onSuccess?: () => void;
};

const LEAVE_TYPES = [
  { value: 'annual', label: 'Annual Leave', balance: 15 },
  { value: 'sick', label: 'Sick Leave', balance: 10 },
  { value: 'casual', label: 'Casual Leave', balance: 5 },
  { value: 'maternity', label: 'Maternity Leave', balance: 90 },
  { value: 'paternity', label: 'Paternity Leave', balance: 14 },
  { value: 'study', label: 'Study Leave', balance: 30 },
  { value: 'compassionate', label: 'Compassionate Leave', balance: 5 },
];

export const LeaveApplicationModal: React.FC<Props> = ({ open, onClose, onSuccess }) => {
  const [step, setStep] = useState<'form' | 'confirm' | 'success'>('form');
  const [leaveType, setLeaveType] = useState('annual');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [reason, setReason] = useState('');
  const [reliefOfficer, setReliefOfficer] = useState('');

  const selectedType = LEAVE_TYPES.find(t => t.value === leaveType);

  const dayCount = startDate && endDate
    ? Math.max(1, Math.ceil((new Date(endDate).getTime() - new Date(startDate).getTime()) / 86400000) + 1)
    : 0;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setStep('confirm');
  };

  const handleConfirm = () => {
    setStep('success');
    setTimeout(() => {
      onSuccess?.();
      handleClose();
    }, 2000);
  };

  const handleClose = () => {
    setStep('form');
    setLeaveType('annual');
    setStartDate('');
    setEndDate('');
    setReason('');
    setReliefOfficer('');
    onClose();
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-lg rounded-2xl bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
          <div className="flex items-center gap-2">
            <CalendarPlus className="h-5 w-5 text-brand-500" />
            <h2 className="text-lg font-semibold text-gray-900">Apply for Leave</h2>
          </div>
          <button onClick={handleClose} className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600">
            <X className="h-5 w-5" />
          </button>
        </div>

        {step === 'form' && (
          <form onSubmit={handleSubmit} className="space-y-4 px-6 py-5">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Leave Type</label>
              <select value={leaveType} onChange={e => setLeaveType(e.target.value)} className="input-field" required>
                {LEAVE_TYPES.map(t => (
                  <option key={t.value} value={t.value}>{t.label} ({t.balance} days available)</option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">Start Date</label>
                <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} className="input-field" required />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">End Date</label>
                <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} className="input-field" min={startDate} required />
              </div>
            </div>

            {dayCount > 0 && (
              <div className="rounded-lg bg-blue-50 px-4 py-2.5">
                <p className="text-sm text-blue-700">
                  <span className="font-semibold">{dayCount} day{dayCount > 1 ? 's' : ''}</span> requested
                  {selectedType && <> &middot; {selectedType.balance - dayCount} days remaining after this request</>}
                </p>
              </div>
            )}

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Relief Officer</label>
              <select value={reliefOfficer} onChange={e => setReliefOfficer(e.target.value)} className="input-field" required>
                <option value="">Select a colleague...</option>
                <option value="ama">Ama Mensah</option>
                <option value="kofi">Kofi Osei</option>
                <option value="abena">Abena Boateng</option>
                <option value="nana">Nana Appiah</option>
              </select>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Reason</label>
              <textarea value={reason} onChange={e => setReason(e.target.value)} rows={3} className="input-field" placeholder="Brief reason for your leave request..." required />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Attachment (optional)</label>
              <div className="flex items-center justify-center rounded-lg border-2 border-dashed border-gray-200 px-4 py-6 text-center hover:border-gray-300">
                <div>
                  <p className="text-sm text-gray-600">Drag & drop or <span className="font-medium text-brand-500 cursor-pointer">browse files</span></p>
                  <p className="mt-1 text-xs text-gray-400">PDF, JPG, PNG up to 5MB</p>
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-3 border-t border-gray-100 pt-4">
              <button type="button" onClick={handleClose} className="btn-secondary text-sm">Cancel</button>
              <button type="submit" className="btn-primary text-sm" disabled={!startDate || !endDate || !reason || !reliefOfficer}>Submit Application</button>
            </div>
          </form>
        )}

        {step === 'confirm' && (
          <div className="space-y-4 px-6 py-5">
            <p className="text-sm text-gray-600">Please confirm your leave application:</p>
            <div className="rounded-lg bg-gray-50 p-4 space-y-2">
              <div className="flex justify-between text-sm"><span className="text-gray-500">Leave Type</span><span className="font-medium text-gray-900">{selectedType?.label}</span></div>
              <div className="flex justify-between text-sm"><span className="text-gray-500">Duration</span><span className="font-medium text-gray-900">{startDate} to {endDate} ({dayCount} days)</span></div>
              <div className="flex justify-between text-sm"><span className="text-gray-500">Relief Officer</span><span className="font-medium text-gray-900">{reliefOfficer}</span></div>
              <div className="flex justify-between text-sm"><span className="text-gray-500">Reason</span><span className="font-medium text-gray-900 text-right max-w-[200px]">{reason}</span></div>
            </div>
            <div className="flex justify-end gap-3 border-t border-gray-100 pt-4">
              <button onClick={() => setStep('form')} className="btn-secondary text-sm">Back to Edit</button>
              <button onClick={handleConfirm} className="btn-primary text-sm">Confirm & Submit</button>
            </div>
          </div>
        )}

        {step === 'success' && (
          <div className="flex flex-col items-center gap-4 px-6 py-10 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-100">
              <CheckCircle className="h-8 w-8 text-emerald-600" />
            </div>
            <h3 className="text-lg font-semibold text-gray-900">Leave Application Submitted</h3>
            <p className="text-sm text-gray-500">Your leave request has been sent to your supervisor for approval. You will be notified once a decision is made.</p>
          </div>
        )}
      </div>
    </div>
  );
};
