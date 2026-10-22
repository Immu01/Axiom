export function parseThink(content) {
  if (!content) return { thinking: "", isThinking: false, answer: "" };
  const openTag = "<think>";
  const closeTag = "</think>";
  const thoughts = [];
  let answer = "";
  let cursor = 0;
  let isThinking = false;

  while (cursor < content.length) {
    const open = content.indexOf(openTag, cursor);
    if (open === -1) {
      answer += content.slice(cursor);
      break;
    }
    answer += content.slice(cursor, open);
    const bodyStart = open + openTag.length;
    const close = content.indexOf(closeTag, bodyStart);
    if (close === -1) {
      thoughts.push(content.slice(bodyStart));
      isThinking = true;
      break;
    }
    thoughts.push(content.slice(bodyStart, close));
    cursor = close + closeTag.length;
  }

  return {
    thinking: thoughts.join("\n").trim(),
    isThinking,
    answer: answer.trim(),
  };
}
