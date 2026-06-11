export const pressableFeedback = (pressed: boolean, disabled = false) => ({
  opacity: disabled ? 0.55 : pressed ? 0.82 : 1,
  transform: [{ scale: pressed ? 0.97 : 1 }],
});

export const pressableCardFeedback = (pressed: boolean, disabled = false) => ({
  opacity: disabled ? 0.55 : pressed ? 0.9 : 1,
  transform: [{ scale: pressed ? 0.985 : 1 }],
});
