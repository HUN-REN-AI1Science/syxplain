/**
 * FeedbackDialog Component
 * Dialog for submitting bug reports and feature requests
 */

import React, { useState, useRef } from 'react';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { InputText } from 'primereact/inputtext';
import { InputTextarea } from 'primereact/inputtextarea';
import { Button } from 'primereact/button';
import { Toast } from 'primereact/toast';
import { feedbackService } from '@services/api';
import type { FeedbackCategory, FeedbackContext } from '@/types';

interface FeedbackDialogProps {
  visible: boolean;
  onHide: () => void;
  context: FeedbackContext;
}

const CATEGORY_OPTIONS = [
  { label: 'Bug Report', value: 'bug' as FeedbackCategory },
  { label: 'Feature Request', value: 'feature' as FeedbackCategory },
];

const PLACEHOLDERS: Record<FeedbackCategory, string> = {
  bug: 'Describe what happened, what you expected, and steps to reproduce...',
  feature: 'Describe the feature you would like and how it would help your workflow...',
};

export const FeedbackDialog: React.FC<FeedbackDialogProps> = ({ visible, onHide, context }) => {
  const [category, setCategory] = useState<FeedbackCategory>('bug');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const toast = useRef<Toast>(null);

  const isValid = title.trim().length >= 1 && title.length <= 100 && description.trim().length >= 10 && description.length <= 2000;

  const resetForm = () => {
    setCategory('bug');
    setTitle('');
    setDescription('');
  };

  const handleSubmit = async () => {
    if (!isValid) return;
    setSubmitting(true);
    try {
      const response = await feedbackService.submit({
        category,
        title: title.trim(),
        description: description.trim(),
        context,
      });
      toast.current?.show({
        severity: 'success',
        summary: 'Thank you!',
        detail: response.data.message,
        life: 4000,
      });
      resetForm();
      onHide();
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number } };
      const detail = axiosErr.response?.status === 429
        ? 'Too many submissions. Please wait a minute and try again.'
        : 'Failed to submit feedback. Please try again.';
      toast.current?.show({ severity: 'error', summary: 'Error', detail, life: 5000 });
    } finally {
      setSubmitting(false);
    }
  };

  const handleHide = () => {
    if (!submitting) {
      resetForm();
      onHide();
    }
  };

  const footer = (
    <div className="flex justify-end gap-2">
      <Button
        label="Cancel"
        icon="pi pi-times"
        className="p-button-text"
        onClick={handleHide}
        disabled={submitting}
      />
      <Button
        label="Submit"
        icon="pi pi-send"
        onClick={handleSubmit}
        disabled={!isValid || submitting}
        loading={submitting}
      />
    </div>
  );

  return (
    <>
      <Toast ref={toast} />
      <Dialog
        header="Send Feedback"
        visible={visible}
        onHide={handleHide}
        footer={footer}
        style={{ width: '500px' }}
        modal
        closable={!submitting}
        draggable={false}
      >
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <label htmlFor="fb-category" className="font-semibold text-sm">
              Category
            </label>
            <Dropdown
              id="fb-category"
              value={category}
              options={CATEGORY_OPTIONS}
              onChange={(e) => setCategory(e.value)}
              className="w-full"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="fb-title" className="font-semibold text-sm">
              Title
            </label>
            <InputText
              id="fb-title"
              value={title}
              onChange={(e) => setTitle(e.target.value.slice(0, 100))}
              placeholder="Brief summary"
              className="w-full"
              maxLength={100}
            />
            <small className="text-right text-slate-400">{title.length}/100</small>
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="fb-description" className="font-semibold text-sm">
              Description
            </label>
            <InputTextarea
              id="fb-description"
              value={description}
              onChange={(e) => setDescription(e.target.value.slice(0, 2000))}
              placeholder={PLACEHOLDERS[category]}
              rows={6}
              className="w-full"
              maxLength={2000}
              autoResize
            />
            <small className="text-right text-slate-400">{description.length}/2000</small>
          </div>

          <div className="flex items-center gap-2 text-sm text-slate-500 bg-slate-50 rounded p-2">
            <i className="pi pi-info-circle" />
            <span>Technical context (current page, run ID, browser) will be automatically included.</span>
          </div>
        </div>
      </Dialog>
    </>
  );
};

export default FeedbackDialog;
