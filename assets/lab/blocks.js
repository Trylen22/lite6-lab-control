/* Lab blocks: UFACTORY Studio block types for the Lite 6, plus a toolbox and
 * themes. Type names (move_joints, set_suction_cup, set_angle_speed, …) and
 * the field names seen in Studio exports are kept so projects round-trip.
 * Field order matches UFACTORY's converter, which reads fields by position.
 */
(function () {
  "use strict";
  if (!window.Blockly) return;
  const B = window.Blockly;
  const BLUE = "#003087";
  const SLATE = "#4D5F80";
  const RED = "#CB333B";
  const GOLD = "#B87A14";

  const num = (name, value, min, max) => ({ type: "field_number", name, value, ...(min != null && { min }), ...(max != null && { max }), precision: 0.1 });
  const chain = { previousStatement: null, nextStatement: null };

  B.common.defineBlocksWithJsonArray([
    {
      type: "move_joints",
      message0: "move joints J1 %1 J2 %2 J3 %3",
      args0: [num("i", 0), num("j", 0), num("k", 0)],
      message1: "J4 %1 J5 %2 J6 %3",
      args1: [num("l", 0), num("m", 0), num("n", 0)],
      message2: "blend radius %1 mm  wait %2",
      args2: [num("r", 0, 0), { type: "field_checkbox", name: "wait", checked: false }],
      ...chain,
      colour: BLUE,
      tooltip: "Turn every joint to these angles (degrees) at the joint speed.",
    },
    {
      type: "move_cartesian",
      message0: "move to X %1 Y %2 Z %3 mm",
      args0: [num("x", 290), num("y", 20), num("z", 266)],
      message1: "roll %1 pitch %2 yaw %3",
      args1: [num("roll", 180), num("pitch", 0), num("yaw", 0)],
      message2: "blend radius %1 mm  wait %2",
      args2: [num("r", 0, 0), { type: "field_checkbox", name: "wait", checked: false }],
      ...chain,
      colour: BLUE,
      tooltip: "Move the tool in a straight line to this position and angle.",
    },
    {
      type: "move",
      message0: "move %1 %2 mm  wait %3",
      args0: [
        {
          type: "field_dropdown",
          name: "orientation",
          options: [
            ["forward", "forward"],
            ["backward", "backward"],
            ["left", "left"],
            ["right", "right"],
            ["up", "up"],
            ["down", "down"],
          ],
        },
        num("distance", 50, 0),
        { type: "field_checkbox", name: "wait", checked: false },
      ],
      ...chain,
      colour: BLUE,
      tooltip: "Move the tool straight by this distance, along the robot's axes.",
    },
    { type: "reset", message0: "go home (all joints to 0)", ...chain, colour: BLUE },
    { type: "set_angle_speed", message0: "set joint speed %1 °/s", args0: [num("speed", 20, 1, 180)], ...chain, colour: SLATE },
    { type: "set_angle_acceleration", message0: "set joint acceleration %1 °/s²", args0: [num("acc", 500, 1, 1145)], ...chain, colour: SLATE },
    { type: "set_speed", message0: "set tool speed %1 mm/s", args0: [num("speed", 100, 1, 500)], ...chain, colour: SLATE },
    { type: "set_acceleration", message0: "set tool acceleration %1 mm/s²", args0: [num("acc", 2000, 1, 50000)], ...chain, colour: SLATE },
    {
      type: "set_suction_cup",
      message0: "suction %1  wait %2",
      args0: [
        { type: "field_dropdown", name: "trigger", options: [["ON", "ON"], ["OFF", "OFF"]] },
        { type: "field_checkbox", name: "wait", checked: false },
      ],
      ...chain,
      colour: RED,
      tooltip: "Turn the vacuum cup on to grab, off to let go.",
    },
    {
      type: "wait",
      message0: "wait %1 seconds",
      args0: [{ type: "input_value", name: "sec", check: "Number" }],
      inputsInline: true,
      ...chain,
      colour: GOLD,
    },
    {
      type: "loop_run_forever",
      message0: "repeat forever %1 %2",
      args0: [{ type: "input_dummy" }, { type: "input_statement", name: "DO" }],
      ...chain,
      style: "loop_blocks",
    },
    {
      type: "lab_unsupported",
      message0: "Studio block %1 (not simulated)",
      args0: [{ type: "field_label_serializable", name: "TYPE", text: "?" }],
      ...chain,
      colour: "#8C8279",
      tooltip: "Imported from Studio. Kept as-is on export; the simulator skips it.",
    },
  ]);

  const shadowNumber = (n) => ({ shadow: { type: "math_number", fields: { NUM: n } } });
  window.LabToolbox = {
    kind: "categoryToolbox",
    contents: [
      {
        kind: "category",
        name: "Motion",
        colour: BLUE,
        contents: ["move_joints", "move_cartesian", "move", "reset"].map((type) => ({ kind: "block", type })),
      },
      {
        kind: "category",
        name: "Speed",
        colour: SLATE,
        contents: ["set_angle_speed", "set_angle_acceleration", "set_speed", "set_acceleration"].map((type) => ({ kind: "block", type })),
      },
      { kind: "category", name: "Suction", colour: RED, contents: [{ kind: "block", type: "set_suction_cup" }] },
      { kind: "category", name: "Timing", colour: GOLD, contents: [{ kind: "block", type: "wait", inputs: { sec: shadowNumber(1) } }] },
      {
        kind: "category",
        name: "Loops",
        categorystyle: "loop_category",
        contents: [
          { kind: "block", type: "controls_repeat_ext", inputs: { TIMES: shadowNumber(3) } },
          { kind: "block", type: "loop_run_forever" },
          { kind: "block", type: "controls_whileUntil" },
        ],
      },
      {
        kind: "category",
        name: "Logic",
        categorystyle: "logic_category",
        contents: ["controls_if", "logic_compare", "logic_operation", "logic_negate", "logic_boolean"].map((type) => ({ kind: "block", type })),
      },
      {
        kind: "category",
        name: "Math",
        categorystyle: "math_category",
        contents: [{ kind: "block", type: "math_number" }, { kind: "block", type: "math_arithmetic" }],
      },
      { kind: "category", name: "Variables", categorystyle: "variable_category", custom: "VARIABLE" },
      { kind: "category", name: "Functions", categorystyle: "procedure_category", custom: "PROCEDURE" },
    ],
  };

  const font = { family: '"Avenir Next", "Avenir", "Nunito Sans", system-ui, sans-serif', weight: "700", size: 12 };
  window.LabThemes = {
    light: B.Theme.defineTheme("labdeck-light", {
      base: B.Themes.Classic,
      fontStyle: font,
      componentStyles: {
        workspaceBackgroundColour: "#f7f9fc",
        toolboxBackgroundColour: "#ffffff",
        toolboxForegroundColour: "#141c2e",
        flyoutBackgroundColour: "#edf2f8",
        flyoutForegroundColour: "#141c2e",
        flyoutOpacity: 0.96,
        scrollbarColour: "#9fb1d3",
        insertionMarkerColour: "#003087",
        cursorColour: "#cb333b",
      },
    }),
    dark: B.Theme.defineTheme("labdeck-dark", {
      base: B.Themes.Classic,
      fontStyle: font,
      componentStyles: {
        workspaceBackgroundColour: "#05070c",
        toolboxBackgroundColour: "#0b1220",
        toolboxForegroundColour: "#f2f5fa",
        flyoutBackgroundColour: "#0e1a33",
        flyoutForegroundColour: "#f2f5fa",
        flyoutOpacity: 0.96,
        scrollbarColour: "#33466e",
        insertionMarkerColour: "#ffffff",
        cursorColour: "#fbae40",
      },
    }),
  };
})();
