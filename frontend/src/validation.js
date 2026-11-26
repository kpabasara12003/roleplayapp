/* Shared pure validation for authoring. Backend validation remains authoritative. */
(function () {
  const limits = {title:100, place:200, time:200, introduction:12000, greeting:4000,
    name:50, gender:20, personality:4000, backstory:8000, example_dialogue:4000,
    appearance:2000, role_description:2000, keyword:50, description:12000, category:50};
  function textErrors(data, fields, required = []) {
    const errors = {};
    for (const field of fields) {
      const value = data[field] ?? '';
      if (typeof value !== 'string') { errors[field] = 'Use text for this field.'; continue; }
      if (required.includes(field) && !value.trim()) errors[field] = 'This field is required.';
      else if (value.length > limits[field]) errors[field] = `Use at most ${limits[field]} characters.`;
    }
    return errors;
  }
  function character(data) {
    const errors = textErrors(data, ['name','gender','personality','backstory','example_dialogue','appearance','greeting','role_description'], ['name']);
    if (data.age !== '' && data.age != null && (!/^\d+$/.test(String(data.age)) || Number(data.age) > 10000)) errors.age = 'Enter a whole number from 0 to 10000, or leave blank.';
    for (const field of ['likes','dislikes']) {
      const values = String(data[field] || '').split(',').map(v => v.trim()).filter(Boolean);
      if (values.length > 30 || values.some(v => v.length > 100)) errors[field] = 'Use up to 30 entries, each at most 100 characters.';
    }
    return errors;
  }
  function parseObject(text, label) {
    if (text.length > 262144) throw new Error(`${label} exceeds the 256 KB editor limit.`);
    let result;
    try { result = JSON.parse(text); } catch (error) { throw new Error(`${label}: ${error.message}`); }
    if (!result || Array.isArray(result) || typeof result !== 'object') throw new Error(`${label} must be a JSON object.`);
    function inspect(value, depth = 0) {
      if (depth > 40) throw new Error(`${label} is nested too deeply.`);
      if (!value || typeof value !== 'object') return;
      for (const key of Object.keys(value)) {
        if (['__proto__','constructor','prototype'].includes(key)) throw new Error(`${label} contains a reserved object key.`);
        inspect(value[key], depth + 1);
      }
    }
    inspect(result);
    return result;
  }
  window.RPValidation = {limits, textErrors, character, parseObject};
})();
