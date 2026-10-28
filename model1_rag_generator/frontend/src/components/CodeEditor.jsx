import Editor from "@monaco-editor/react";

export default function CodeEditor({ value, onChange, language = "python", readOnly = false }) {
  return (
    <Editor
      height="100%"
      language={language}
      theme="vs-dark"
      value={value}
      onChange={readOnly ? undefined : (v) => onChange?.(v ?? "")}
      options={{
        minimap: { enabled: false },
        fontSize: 13,
        wordWrap: "on",
        readOnly,
      }}
    />
  );
}
