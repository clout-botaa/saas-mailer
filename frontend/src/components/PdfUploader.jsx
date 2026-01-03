import React, { useState } from 'react';

export default function PdfUploader({ onParsed }) {
  const [file, setFile] = useState(null);
  const [parsing, setParsing] = useState(false);
  const [parsed, setParsed] = useState(null);
  const [mappings, setMappings] = useState({});

  const handleFile = (e) => setFile(e.target.files[0]);

  async function submit() {
    if (!file) return;
    setParsing(true);
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch('/api/parse-pdf', { method: 'POST', body: fd });
    const data = await res.json();
    setParsed(data);
    // Naive: try extract simple fields from lines
    const columns = (data.text || '').split('\n').slice(0, 20);
    const suggested = {};
    columns.forEach((c, i) => { suggested[`col${i}`] = c.slice(0, 80); });
    setMappings(suggested);
    setParsing(false);
    if (onParsed) onParsed(data);
  }

  return (
    <div className="p-4">
      <h3 className="text-lg font-semibold">Upload PDF</h3>
      <input type="file" accept="application/pdf" onChange={handleFile} />
      <div className="mt-2">
        <button className="btn bg-blue-600 text-white px-3 py-1" onClick={submit} disabled={parsing || !file}>
          {parsing ? 'Parsing…' : 'Parse PDF'}
        </button>
      </div>

      {parsed && (
        <div className="mt-4">
          <h4 className="font-medium">Parsed Preview</h4>
          <div className="mt-2 max-h-48 overflow-auto bg-gray-50 p-2">{parsed.text}</div>

          <h4 className="mt-4 font-medium">Variable Mapping</h4>
          <p className="text-sm text-gray-600">Map template variables to PDF-derived columns</p>
          <div className="mt-2">
            {Object.keys(mappings).map((k) => (
              <div key={k} className="flex items-center gap-2 py-1">
                <label className="w-24 text-sm text-gray-700">{k}</label>
                <input
                  value={mappings[k]}
                  onChange={(e) => setMappings(s => ({ ...s, [k]: e.target.value }))}
                  className="flex-1 border rounded px-2 py-1"
                />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
