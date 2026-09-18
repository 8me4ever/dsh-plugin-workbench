// src/index.ts
var name = "dsh-plugin-workbench";
var inject = [];
function apply(ctx) {
  ctx.logger.info("[dsh-plugin-workbench] host half mounted \u2014 UI comes from the client half");
}
export {
  apply,
  inject,
  name
};
