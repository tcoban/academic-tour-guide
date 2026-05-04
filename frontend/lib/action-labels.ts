export const ACTION_LABELS = {
  approveEvidence: "Approve evidence",
  buildAnonymousTourProposal: "Build anonymous tour proposal",
  createSpeakerTourDraft: "Create speaker tour draft",
  draftInvitation: "Create KOF invitation draft",
  markSent: "Mark sent",
  reviewBlockedSlots: "Inspect blocked KOF slots",
  runRealSync: "Run real source sync",
  setWeeklySlot: "Set weekly KOF slot",
  viewDetails: "View details",
} as const;

export const ALLOWED_DUPLICATE_ACTION_LABELS = ["Cancel edit", ACTION_LABELS.viewDetails] as const;
