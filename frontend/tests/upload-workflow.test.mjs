import test from "node:test";
import assert from "node:assert/strict";
import {uploadWorkflow, uploadReason, canProcessUpload} from "../src/lib/uploadWorkflow.ts";

test("review rejection never marks parsing or indexing as complete", () => {
  assert.deepEqual(uploadWorkflow("rejected").steps.map(s=>s.state),["done","blocked","waiting","waiting"]);
  assert.equal(canProcessUpload("rejected"),false);
  assert.equal(canProcessUpload("pending"),false);
});
test("processing is a combined uncompleted stage until indexed", () => {
  assert.deepEqual(uploadWorkflow("processing").steps.map(s=>s.state),["done","done","current","waiting"]);
  assert.ok(uploadWorkflow("indexed").steps.every(s=>s.state==="done"));
  assert.equal(uploadWorkflow("indexed").label,"关键词可检索");
});
test("failed and unavailable uploads retain approval but never imply available documents", () => {
  for (const status of ["failed","dependency_unavailable"]) {
    assert.deepEqual(uploadWorkflow(status).steps.map(s=>s.state),["done","done","blocked","waiting"]);
    assert.equal(canProcessUpload(status),true);
  }
  assert.match(uploadReason("pdf_requires_ocr"),/OCR/);
  assert.equal(uploadReason("The reviewer requested a clearer original"),"The reviewer requested a clearer original");
});
test("unknown server states do not infer approval, progress or processing rights", () => {
  for (const status of ["future_backend_state","constructor","__proto__"]) {
    assert.equal(uploadWorkflow(status).known,false);
    assert.equal(uploadWorkflow(status).label,"未知处理状态");
    assert.equal(uploadReason(status),status);
  }
  assert.deepEqual(uploadWorkflow("future_backend_state").steps.map(s=>s.state),["done","waiting","waiting","waiting"]);
  assert.equal(canProcessUpload("future_backend_state"),false);
});
