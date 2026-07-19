const confirmation = document.querySelector(".booking-success-card");

if (confirmation) {
  const redirectUrl = confirmation.dataset.redirectUrl;
  const redirectDelay = Number(confirmation.dataset.redirectDelay) || 5000;

  window.setTimeout(() => {
    window.location.href = redirectUrl;
  }, redirectDelay);
}
