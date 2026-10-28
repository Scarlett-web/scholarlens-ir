import test from "node:test";
import assert from "node:assert/strict";
import { normalizeSearchPage, normalizeSearchField } from "../src/lib/searchParams.ts";

test("malformed shared search links recover to a valid API page", () => {
  for (const value of [null,"","NaN","Infinity","0","-1","1.5","1e100","99999999999999999","1667"]) {
    assert.equal(normalizeSearchPage(value),1,String(value));
  }
  assert.equal(normalizeSearchPage("11"),11);
  assert.equal(normalizeSearchPage("1666"),1666);
});

test("semantic deep links and author suggestions cannot submit unsupported fields", () => {
  for (const field of ["authors","date","affiliation","address","unknown",null]) assert.equal(normalizeSearchField(field,"semantic"),"all");
  for (const field of ["title","fulltext","all"]) assert.equal(normalizeSearchField(field,"semantic"),field);
  assert.equal(normalizeSearchField("authors","keyword"),"authors");
  assert.equal(normalizeSearchField("authors","hybrid"),"authors");
});
