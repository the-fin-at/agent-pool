const copyButton = document.querySelector('#copy-setup');
const setupPrompt = document.querySelector('#setup-prompt');
const feedback = document.querySelector('#copy-feedback');

if (copyButton && setupPrompt && feedback && navigator.clipboard?.writeText) {
  copyButton.hidden = false;
  copyButton.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(setupPrompt.textContent.trim());
      feedback.textContent = 'Copied. Paste it into Codex or Claude Code to get started.';
    } catch {
      feedback.textContent = 'Select and copy the prompt above, then paste it into your agent.';
    }
  });
}
