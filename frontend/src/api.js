const API_BASE_URL = 'https://axiom-backend-02r9.onrender.com';

export async function sendMessageToBackend(message, model = 'auto') {
  const response = await fetch(`${API_BASE_URL}/api/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message, model }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Network error occurred while contacting Axiom API.');
  }

  return await response.json();
}