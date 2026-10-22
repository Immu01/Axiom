import { parseThink } from "./parseThink.js";
import { plainText } from "./voice.js";
import assert from "node:assert/strict";

{
  const r = parseThink("hello");
  assert.equal(r.answer, "hello");
  assert.equal(r.isThinking, false);
}
{
  const r = parseThink("<think>plan</think>\nAnswer");
  assert.equal(r.thinking, "plan");
  assert.equal(r.answer, "Answer");
  assert.equal(r.isThinking, false);
}
{
  const r = parseThink("<think>still going");
  assert.equal(r.isThinking, true);
  assert.equal(r.answer, "");
}
{
  const r = parseThink("Before <think>first</think> middle <think>second</think> after");
  assert.equal(r.thinking, "first\nsecond");
  assert.equal(r.answer, "Before  middle  after");
  assert.equal(r.isThinking, false);
}
{
  const r = parseThink("Visible <think>unfinished");
  assert.equal(r.thinking, "unfinished");
  assert.equal(r.answer, "Visible");
  assert.equal(r.isThinking, true);
}
assert.equal(plainText("<think>private plan</think>Public answer."), "Public answer.");
assert.equal(plainText("Public answer. <think>unfinished"), "Public answer.");
console.log("parseThink ok");
