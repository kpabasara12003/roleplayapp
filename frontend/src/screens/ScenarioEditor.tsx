// src/screens/ScenarioEditor.tsx → window.RPScreens.ScenarioEditor

(function() {
  const { useState, useEffect, useCallback, useRef } = React;
  const { ErrorBanner, LoadingWrap, ConfirmDialog, Modal } = window.RPComponents;
  const { useToast } = window.RPComponents;
  const Api = window.RPApi;
  const V = window.RPValidation;
  function validationError(fields) { return {status:422,fieldErrors:fields}; }
  function firstInvalid(fields,prefix) { document.getElementById(prefix+Object.keys(fields)[0])?.focus(); }
  function useDraftClose(form,saving,onClose) {
    const initial=useRef(JSON.stringify(form));
    const dirty=JSON.stringify(form)!==initial.current;
    useEffect(()=>{const guard=e=>{if(dirty){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',guard);return()=>window.removeEventListener('beforeunload',guard);},[dirty]);
    return ()=>{if(!saving&&(!dirty||window.confirm('Discard unsaved form changes?')))onClose();};
  }


  // ---- Character form modal ----
  function CharacterModal({ scenarioId, character, onSave, onClose }) {
    const [form, setForm] = useState({
      name: character?.name || '',
      gender: character?.gender || '',
      age: character?.age ?? '',
      personality: character?.personality || '',
      likes: (character?.likes || []).join(', '),
      dislikes: (character?.dislikes || []).join(', '),
      backstory: character?.backstory || '',
      example_dialogue: character?.example_dialogue || '',
      appearance: character?.appearance || '',
      greeting: character?.greeting || '',
      role_description: character?.role_description || '',
      is_ai: character?.is_ai ?? true,
    });
    const [saving, setSaving] = useState(false);
    const [err, setErr]       = useState(null);
    const submitting=useRef(false);
    const requestClose=useDraftClose(form,saving,onClose);

    function set(k, v) { setErr(null); setForm(f => ({ ...f, [k]: v })); }

    async function handleSave(e) {
      e.preventDefault();
      if (submitting.current) return;
      const errors=V.character(form);
      if (Object.keys(errors).length) {setErr(validationError(errors));firstInvalid(errors,'ch-');return;}
      submitting.current=true;
      setSaving(true);
      setErr(null);
      const payload = {
        ...form,
        name:form.name.trim(), age:form.age===''?null:Number(form.age),
        likes: form.likes.split(',').map(s => s.trim()).filter(Boolean),
        dislikes: form.dislikes.split(',').map(s => s.trim()).filter(Boolean),
      };
      try {
        let result;
        if (character?.id) {
          delete payload.is_ai;
          result = await Api.updateCharacter(character.id, payload);
        } else {
          result = await Api.createCharacter(scenarioId, payload);
        }
        onSave(result);
      } catch (e) {
        setErr(e);
      } finally {
        submitting.current=false;
        setSaving(false);
      }
    }

    const F = (label, id, type, value, onChange, extra) =>
      React.createElement(
        'div', { className: 'input-group' },
        React.createElement('label', { className: 'label', htmlFor: id }, label),
        React.createElement('input', { id, className: 'input', maxLength:V.limits[id.replace('ch-','')], 'aria-invalid':!!err?.fieldErrors?.[id.replace('ch-','')], type: type || 'text', value, onChange: e => onChange(e.target.value), disabled: saving, ...extra })
      );

    const footer = React.createElement(
      React.Fragment, null,
      React.createElement('button', { className: 'btn-secondary', onClick: requestClose, disabled: saving }, 'Cancel'),
      React.createElement('button', { className: 'btn-primary', onClick: handleSave, disabled: saving },
        saving ? 'Saving...' : (character?.id ? 'Update Character' : 'Add Character'))
    );

    return React.createElement(
      Modal, { title: character?.id ? 'Edit Character' : 'Add Character', onClose:requestClose, footer, wide: true, busy:saving },
      React.createElement(ErrorBanner, { error: err }),
      React.createElement('div', { className: 'form-row' },
        React.createElement('div', { className: 'form-col' }, F('Name *', 'ch-name', 'text', form.name, v => set('name', v), { autoFocus: true, required:true })),
        React.createElement('div', { className: 'form-col' }, F('Gender', 'ch-gender', 'text', form.gender, v => set('gender', v))),
        React.createElement('div', { className: 'form-col' }, F('Age (optional)', 'ch-age', 'number', form.age, v => set('age', v), {min:0,max:10000,step:1}))
      ),
      React.createElement('div', { className: 'input-group' },
        React.createElement('label', { className: 'label', htmlFor: 'ch-personality' }, 'Personality'),
        React.createElement('textarea', { id: 'ch-personality', maxLength:4000, className: 'textarea', value: form.personality, onChange: e => set('personality', e.target.value), disabled: saving, rows: 2 })
      ),
      React.createElement('div', { className: 'form-row' },
        React.createElement('div', { className: 'form-col' },
          React.createElement('div', { className: 'input-group' },
            React.createElement('label', { className: 'label', htmlFor: 'ch-likes' }, 'Likes (comma-separated)'),
            React.createElement('input', { disabled:saving, id: 'ch-likes', className: 'input', value: form.likes, onChange: e => set('likes', e.target.value) })
          )
        ),
        React.createElement('div', { className: 'form-col' },
          React.createElement('div', { className: 'input-group' },
            React.createElement('label', { className: 'label', htmlFor: 'ch-dislikes' }, 'Dislikes (comma-separated)'),
            React.createElement('input', { disabled:saving, id: 'ch-dislikes', className: 'input', value: form.dislikes, onChange: e => set('dislikes', e.target.value) })
          )
        )
      ),
      React.createElement('div', { className: 'input-group' },
        React.createElement('label', { className: 'label', htmlFor: 'ch-backstory' }, 'Backstory'),
        React.createElement('textarea', { disabled:saving, id: 'ch-backstory', maxLength:8000, className: 'textarea', value: form.backstory, onChange: e => set('backstory', e.target.value), rows: 3 })
      ),
      React.createElement('div', { className: 'input-group' },
        React.createElement('label', { className: 'label', htmlFor: 'ch-appearance' }, 'Appearance'),
        React.createElement('input', { disabled:saving, id: 'ch-appearance', maxLength:2000, className: 'input', value: form.appearance, onChange: e => set('appearance', e.target.value) })
      ),
      React.createElement('div', { className: 'input-group' },
        React.createElement('label', { className: 'label', htmlFor: 'ch-greeting' }, 'Greeting'),
        React.createElement('textarea', { disabled:saving, id: 'ch-greeting', maxLength:4000, className: 'textarea', value: form.greeting, onChange: e => set('greeting', e.target.value), rows: 2 })
      ),
      React.createElement('div', { className: 'input-group' },
        React.createElement('label', { className: 'label', htmlFor: 'ch-role_description' }, 'Role Description'),
        React.createElement('textarea', { disabled:saving, id: 'ch-role_description', maxLength:2000, className: 'textarea', value: form.role_description, onChange: e => set('role_description', e.target.value), rows: 2 })
      ),
      React.createElement('div', { className: 'input-group' },
        React.createElement('label', { className: 'label', htmlFor: 'ch-example_dialogue' }, 'Example Dialogue'),
        React.createElement('textarea', { disabled:saving, id: 'ch-example_dialogue', maxLength:4000, className: 'textarea', value: form.example_dialogue, onChange: e => set('example_dialogue', e.target.value), rows: 3 })
      ),
      React.createElement('label', { className: 'checkbox-label' },
        React.createElement('input', { type: 'checkbox', disabled:saving||!!character?.id, checked: form.is_ai, onChange: e => set('is_ai', e.target.checked) }),
        character?.id ? 'AI-controlled character (type is fixed after creation)' : 'AI-controlled character'
      )
    );
  }

  // ---- Lore item modal ----
  function LoreModal({ scenarioId, lore, onSave, onClose }) {
    const [form, setForm] = useState({
      keyword: lore?.keyword || '',
      description: lore?.description || '',
      category: lore?.category || '',
    });
    const [saving, setSaving] = useState(false);
    const [err, setErr]       = useState(null);
    const submitting=useRef(false);
    const requestClose=useDraftClose(form,saving,onClose);

    function set(k, v) { setErr(null); setForm(f => ({ ...f, [k]: v })); }

    async function handleSave(e) {
      e.preventDefault();
      if (submitting.current) return;
      const errors=V.textErrors(form,['keyword','description','category'],['keyword','description']);
      if (Object.keys(errors).length) {setErr(validationError(errors));firstInvalid(errors,'lore-');return;}
      submitting.current=true;
      setSaving(true);
      setErr(null);
      try {
        let result;
        if (lore?.id) {
          result = await Api.updateLore(scenarioId, lore.id, form);
        } else {
          result = await Api.createLore(scenarioId, form);
        }
        onSave(result);
      } catch (e) {
        setErr(e);
      } finally {
        submitting.current=false;
        setSaving(false);
      }
    }

    const footer = React.createElement(
      React.Fragment, null,
      React.createElement('button', { className: 'btn-secondary', onClick: requestClose, disabled:saving }, 'Cancel'),
      React.createElement('button', { className: 'btn-primary', onClick: handleSave, disabled: saving },
        saving ? 'Saving...' : (lore?.id ? 'Update' : 'Add Lore'))
    );

    return React.createElement(
      Modal, { title: lore?.id ? 'Edit Lore' : 'Add Lore', onClose:requestClose, footer, busy:saving },
      React.createElement(ErrorBanner, { error: err }),
      React.createElement('div', { className: 'input-group' },
        React.createElement('label', { className: 'label', htmlFor: 'lore-keyword' }, 'Keyword *'),
        React.createElement('input', { disabled:saving, id: 'lore-keyword', maxLength:50, className: 'input', value: form.keyword, onChange: e => set('keyword', e.target.value), autoFocus: true })
      ),
      React.createElement('div', { className: 'input-group' },
        React.createElement('label', { className: 'label', htmlFor: 'lore-category' }, 'Category'),
        React.createElement('input', { disabled:saving, id: 'lore-category', maxLength:50, className: 'input', value: form.category, onChange: e => set('category', e.target.value) })
      ),
      React.createElement('div', { className: 'input-group' },
        React.createElement('label', { className: 'label', htmlFor: 'lore-description' }, 'Description *'),
        React.createElement('textarea', { disabled:saving, id: 'lore-description', maxLength:12000, className: 'textarea', value: form.description, onChange: e => set('description', e.target.value), rows: 4 })
      )
    );
  }

  // ---- Main ScenarioEditor ----
  function ScenarioEditor({ scenarioId, onBack }) {
    const toast = useToast();
    const [tab, setTab]           = useState('basic');
    const [scenario, setScenario] = useState(null);
    const [characters, setCharacters] = useState([]);
    const [discoveryTerms,setDiscoveryTerms]=useState([]);
    const [lore, setLore]         = useState([]);
    const [loading, setLoading]   = useState(true);
    const [error, setError]       = useState(null);
    const [saving, setSaving]     = useState(false);
    const [saveError, setSaveError] = useState(null);

    // Basic form
    const [basic, setBasic] = useState({ title: '', greeting: '', place: '', time: '', introduction: '', is_public: false });

    // Rules/Initial state
    const [rulesJson, setRulesJson]   = useState('{}');
    const [stateJson, setStateJson]   = useState('{}');
    const [jsonError, setJsonError]   = useState(null);
    const [baseline,setBaseline]=useState(null);
    const savingRef=useRef(false);
    const [lastPublished,setLastPublished]=useState(null);
    const selectedDiscovery=basic.discovery||{};
    const adultRequired=discoveryTerms.some(t=>t.requires_adult_cast&&((t.kind==='genre'&&(selectedDiscovery.genres||[]).includes(t.slug))||(t.kind==='tone'&&(selectedDiscovery.tones||[]).includes(t.slug))||(t.kind==='life_stage'&&selectedDiscovery.life_stage===t.slug)));
    const missingAdultAges=adultRequired?characters.filter(c=>c.age==null||c.age<18):[];
    const dirty=!!baseline&&(JSON.stringify(basic)!==baseline.basic||rulesJson!==baseline.rules||stateJson!==baseline.state);
    useEffect(()=>{if(tab==='basic'&&saveError?.fieldErrors)firstInvalid(saveError.fieldErrors,'sc-');},[tab,saveError]);
    useEffect(()=>{window.RPUnsaved=dirty; const guard=e=>{if(dirty){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',guard);return()=>{window.RPUnsaved=false;window.removeEventListener('beforeunload',guard);};},[dirty]);
    function applySaved(s) {
      const values={title:s.title||'',greeting:s.greeting||'',place:s.place||'',time:s.time||'',introduction:s.introduction||'',is_public:!!s.is_public,discovery:s.discovery||{genres:[],tones:[],life_stage:'any'}};
      const rules=JSON.stringify(s.rules||{},null,2),state=JSON.stringify(s.initial_state||{},null,2);
      setScenario(s);setBasic(values);setRulesJson(rules);setStateJson(state);setBaseline({basic:JSON.stringify(values),rules,state});
    }

    // Modals
    const [charModal, setCharModal]   = useState(null); // null | 'new' | character obj
    const [loreModal, setLoreModal]   = useState(null);
    const [publishConfirm, setPublishConfirm] = useState(false);
    const [deleteChar, setDeleteChar] = useState(null);
    const [deleteLore, setDeleteLore] = useState(null);

    const load = useCallback(async () => {
      setLoading(true);
      setError(null);
      try {
        const [s, chars, loreItems, terms] = await Promise.all([
          Api.getScenario(scenarioId),
          Api.getCharacters(scenarioId),
          Api.getLore(scenarioId),
          Api.getCatalogFilters(),
        ]);
        applySaved(s);
        setDiscoveryTerms(terms);
        setCharacters(Array.isArray(chars) ? chars : (chars.characters || chars.items || []));
        setLore(Array.isArray(loreItems) ? loreItems : (loreItems.lore || loreItems.items || []));
      } catch (err) {
        setError(err);
      } finally {
        setLoading(false);
      }
    }, [scenarioId]);

    useEffect(() => { load(); }, [load]);

    async function saveDraft() {
      if (savingRef.current) return;
      setSaveError(null);setJsonError(null);
      const errors=V.textErrors(basic,['title','greeting','place','time','introduction'],['title']);
      if(Object.keys(errors).length){setSaveError(validationError(errors));setTab('basic');firstInvalid(errors,'sc-');return;}
      let rules,initial_state;
      try {rules=V.parseObject(rulesJson,'Rules');initial_state=V.parseObject(stateJson,'Initial state');}
      catch(error){setJsonError(error.message);setTab('rules');return;}
      savingRef.current=true;setSaving(true);
      try {
        const updated=await Api.updateScenario(scenarioId,{...basic,title:basic.title.trim(),rules,initial_state});
        applySaved(updated);toast.success('All draft changes saved.');
      } catch(error){setSaveError(error);}finally{savingRef.current=false;setSaving(false);}
    }
    const saveBasic=saveDraft,saveRules=saveDraft;
    async function handlePublish() {
      setPublishConfirm(false);
      if(dirty||missingAdultAges.length||!characters.some(c=>c.is_ai)){toast.error('Save your draft, add an AI character and check the cast ages before publishing.');return;}
      if(savingRef.current)return;
      savingRef.current=true;setSaving(true);
      try {
        const version=await Api.publishScenario(scenarioId);
        setLastPublished(version.version);
        applySaved({...scenario,is_public:true});
        toast.success(`Version ${version.version} published.`);
      }catch(error){setSaveError(error);}finally{savingRef.current=false;setSaving(false);}
    }

    async function handleDeleteChar(id) {
      try {
        await Api.deleteCharacter(id);
        setCharacters(prev => prev.filter(c => c.id !== id));
        setDeleteChar(null);
        toast.success('Character removed.');
      } catch (err) {
        toast.error(window.RPComponents.formatError(err));
      }
    }

    async function handleDeleteLore(id) {
      try {
        await Api.deleteLore(scenarioId, id);
        setLore(prev => prev.filter(l => l.id !== id));
        setDeleteLore(null);
        toast.success('Lore entry removed.');
      } catch (err) {
        toast.error(window.RPComponents.formatError(err));
      }
    }

    if (loading) return React.createElement(LoadingWrap, null);
    if (error && !scenario) return React.createElement('div',null,React.createElement(ErrorBanner,{error}),React.createElement('button',{className:'btn-secondary',onClick:load},'Retry loading'),React.createElement('button',{className:'btn-ghost',onClick:onBack},'Back to scenarios'));

    const tabs = ['basic', 'cast', 'lore', 'rules', 'publish'];

    return React.createElement(
      'div',
      {className:'scenario-editor'},
      // Back + title
      React.createElement(
        'div',
        { className: 'back-row' },
        React.createElement('button', { className: 'btn-ghost', onClick: onBack, disabled:saving }, '← Back'),
        React.createElement('h2', { style: { margin: 0 } }, scenario?.title || 'Edit Scenario')
      ),

      React.createElement(ErrorBanner, { error, onDismiss: () => setError(null) }),

      React.createElement('div',{className:'editor-statusbar'},React.createElement('span',{role:'status','aria-live':'polite'},saving?'Saving…':dirty?'Unsaved draft changes':'Draft saved'),React.createElement('button',{className:'btn-primary',onClick:saveDraft,disabled:saving||!dirty},'Save draft')),
      React.createElement(ErrorBanner,{error:saveError,onDismiss:()=>setSaveError(null)}),
      // Tab bar
      React.createElement(
        'div',
        { className: 'tabs' },
        tabs.map(t => React.createElement(
          'button',
          { key: t, 'aria-pressed':tab===t, disabled:saving, className: `tab-btn ${tab === t ? 'active' : ''}`, onClick: () => setTab(t) },
          t.charAt(0).toUpperCase() + t.slice(1)
        ))
      ),

      // --- Basic Tab ---
      tab === 'basic' && React.createElement(
        'div',
        { className: 'tab-panel' },
        React.createElement(
          'div',
          { className: 'input-group' },
          React.createElement('label', { className: 'label', htmlFor: 'sc-title' }, 'Title * (up to 100 characters)'),
          React.createElement('input', { disabled:saving, id: 'sc-title', required:true,'aria-invalid':!!saveError?.fieldErrors?.title, maxLength:100, className: 'input', value: basic.title, onChange: e => {setSaveError(null);setBasic(b => ({ ...b, title: e.target.value }));} })
        ),
        React.createElement('p',{className:'editor-help'},'World and setting are optional. A scenario can simply be a conversation or situation between characters. Leave place and era blank if you do not need them.'),
        React.createElement('div', { className: 'form-row' },
          React.createElement('div', { className: 'form-col' },
            React.createElement('div', { className: 'input-group' },
              React.createElement('label', { className: 'label', htmlFor: 'sc-place' }, 'Place / world (optional)'),
              React.createElement('input', { disabled:saving, id: 'sc-place', maxLength:200, className: 'input', value: basic.place, onChange: e => {setSaveError(null);setBasic(b => ({ ...b, place: e.target.value }));} })
            )
          ),
          React.createElement('div', { className: 'form-col' },
            React.createElement('div', { className: 'input-group' },
              React.createElement('label', { className: 'label', htmlFor: 'sc-time' }, 'Time / era (optional)'),
              React.createElement('input', { disabled:saving, id: 'sc-time', maxLength:200, className: 'input', value: basic.time, onChange: e => {setSaveError(null);setBasic(b => ({ ...b, time: e.target.value }));} })
            )
          )
        ),
        React.createElement('div', { className: 'input-group' },
          React.createElement('label', { className: 'label', htmlFor: 'sc-introduction' }, 'Introduction'),
          React.createElement('textarea', { disabled:saving, id: 'sc-introduction', maxLength:12000, className: 'textarea', value: basic.introduction, onChange: e => {setSaveError(null);setBasic(b => ({ ...b, introduction: e.target.value }));}, rows: 4 })
        ),
        React.createElement('div', { className: 'input-group' },
          React.createElement('label', { className: 'label', htmlFor: 'sc-greeting' }, 'Opening Greeting'),
          React.createElement('textarea', { disabled:saving, id: 'sc-greeting', maxLength:4000, className: 'textarea', value: basic.greeting, onChange: e => {setSaveError(null);setBasic(b => ({ ...b, greeting: e.target.value }));}, rows: 3 })
        ),
        React.createElement('div', { className: 'toggle-row', style: { marginBottom: '16px' } },
          React.createElement('div', null,
            React.createElement('div', { className: 'toggle-label' }, 'Public'),
            React.createElement('div', { className: 'toggle-desc' }, 'Show in catalog (requires publishing)')
          ),
          React.createElement('input', { disabled:saving, type: 'checkbox', checked: basic.is_public, onChange: e => {setSaveError(null);setBasic(b => ({ ...b, is_public: e.target.checked }));} })
        ),
        React.createElement('section',{className:'creator-discovery','aria-label':'Discovery categories'},
          React.createElement('h3',null,'Help people find this scenario'),
          React.createElement('p',{className:'editor-help'},'Choose up to 4 genres and 3 tones. Labels become searchable when you publish a new version.'),
          ...[['genre','genres','Genres',4],['tone','tones','Tones',3]].map(([kind,key,label,limit])=>React.createElement('fieldset',{className:'discovery-fieldset',key,disabled:saving},
            React.createElement('legend',{className:'label'},label),React.createElement('div',{className:'discovery-options'},discoveryTerms.filter(t=>t.kind===kind).map(t=>{
              const selected=basic.discovery?.[key]||[];
              return React.createElement('label',{className:'discovery-option',key:t.slug},React.createElement('input',{type:'checkbox',checked:selected.includes(t.slug),disabled:saving||(!selected.includes(t.slug)&&selected.length>=limit),onChange:e=>setBasic(b=>({...b,discovery:{...b.discovery,[key]:e.target.checked?[...selected,t.slug]:selected.filter(v=>v!==t.slug)}}))}),t.label);
            })))),
          React.createElement('div',{className:'input-group'},React.createElement('label',{className:'label',htmlFor:'sc-life-stage'},'Life stage'),React.createElement('select',{id:'sc-life-stage',className:'select',disabled:saving,value:basic.discovery?.life_stage||'any',onChange:e=>setBasic(b=>({...b,discovery:{...b.discovery,life_stage:e.target.value}}))},discoveryTerms.filter(t=>t.kind==='life_stage').map(t=>React.createElement('option',{key:t.slug,value:t.slug},t.label)))),
          React.createElement('p',{className:'editor-help'},'Romance and adult life-stage categories require every cast character to have an age of 18 or older. Youthful themes are also available separately.')),
        React.createElement('button', { className: 'btn-primary', onClick: saveBasic, disabled: saving },
          saving ? 'Saving...' : 'Save all changes')
      ),

      // --- Cast Tab ---
      tab === 'cast' && React.createElement(
        'div',
        { className: 'tab-panel' },
        React.createElement(
          'div',
          { className: 'page-header' },
          React.createElement('h3', null, 'Cast'),
          React.createElement('button', { className: 'btn-primary', onClick: () => setCharModal('new') }, 'Add Character')
        ),
        characters.length === 0
          ? React.createElement(window.RPComponents.EmptyState, { message: 'No characters yet.' })
          : characters.map(c => React.createElement(
              'div', { key: c.id, className: 'list-item' },
              React.createElement(
                'div', { style: { flex: 1 } },
                React.createElement('div', { style: { fontWeight: 600 } }, c.name,
                  React.createElement('span', { className: `tag tag-${c.is_ai ? 'ai' : 'user'}`, style: { marginLeft: '8px' } }, c.is_ai ? 'AI' : 'Player')
                ),
                React.createElement('div', { style: { fontSize: '0.8125rem', color: 'var(--color-text-muted)' } },
                  [c.gender, c.age, c.role_description].filter(v=>v!=null&&v!=='').join(' · ') || 'No details'
                )
              ),
              React.createElement('div', { className: 'list-item-actions' },
                React.createElement('button', { className: 'btn-secondary btn-sm', onClick: () => setCharModal(c) }, 'Edit'),
                React.createElement('button', { className: 'btn-ghost btn-sm', style: { color: 'var(--color-danger)' }, onClick: () => setDeleteChar(c) }, 'Remove')
              )
            ))
      ),

      // --- Lore Tab ---
      tab === 'lore' && React.createElement(
        'div',
        { className: 'tab-panel' },
        React.createElement(
          'div',
          { className: 'page-header' },
          React.createElement('h3', null, 'Lore Entries'),
          React.createElement('button', { className: 'btn-primary', onClick: () => setLoreModal('new') }, 'Add Lore')
        ),
        lore.length === 0
          ? React.createElement(window.RPComponents.EmptyState, { message: 'No lore entries yet.' })
          : lore.map(l => React.createElement(
              'div', { key: l.id, className: 'list-item' },
              React.createElement(
                'div', { style: { flex: 1 } },
                React.createElement('div', { style: { fontWeight: 600 } }, l.keyword,
                  l.category && React.createElement('span', { className: 'tag', style: { marginLeft: '8px' } }, l.category)
                ),
                React.createElement('div', { style: { fontSize: '0.8125rem', color: 'var(--color-text-muted)', marginTop: '2px' } },
                  l.description?.length > 100 ? l.description.slice(0, 100) + '…' : l.description)
              ),
              React.createElement('div', { className: 'list-item-actions' },
                React.createElement('button', { className: 'btn-secondary btn-sm', onClick: () => setLoreModal(l) }, 'Edit'),
                React.createElement('button', { className: 'btn-ghost btn-sm', style: { color: 'var(--color-danger)' }, onClick: () => setDeleteLore(l) }, 'Remove')
              )
            ))
      ),

      // --- Rules Tab ---
      tab === 'rules' && React.createElement(
        'div',
        { className: 'tab-panel' },
        jsonError && React.createElement('div', { className: 'error-banner',role:'alert' }, jsonError),
        React.createElement('p',{className:'editor-help'},'Advanced and optional. Keep the defaults for character dialogue. Add authored commands only when your scenario needs inventory or quest mechanics.'),
        React.createElement('button',{className:'btn-secondary btn-sm',disabled:saving,onClick:()=>{try{setRulesJson(JSON.stringify(V.parseObject(rulesJson,'Rules'),null,2));setStateJson(JSON.stringify(V.parseObject(stateJson,'Initial state'),null,2));setJsonError(null);}catch(error){setJsonError(error.message);}}},'Format JSON'),
        React.createElement(
          'div',
          { className: 'input-group' },
          React.createElement('label', { className: 'label', htmlFor: 'sc-rules' }, 'Rules (JSON)'),
          React.createElement('textarea', { disabled:saving, id: 'sc-rules', className: 'textarea json-editor', value: rulesJson, onChange: e => {setJsonError(null);setRulesJson(e.target.value);}, rows: 10 })
        ),
        React.createElement(
          'div',
          { className: 'input-group' },
          React.createElement('label', { className: 'label', htmlFor: 'sc-state' }, 'Initial State (JSON)'),
          React.createElement('textarea', { disabled:saving, id: 'sc-state', className: 'textarea json-editor', value: stateJson, onChange: e => {setJsonError(null);setStateJson(e.target.value);}, rows: 10 })
        ),
        React.createElement('button', { className: 'btn-primary', onClick: saveRules, disabled: saving },
          saving ? 'Saving...' : 'Save all changes')
      ),

      // --- Publish Tab ---
      tab === 'publish' && React.createElement(
        'div',
        { className: 'tab-panel' },
        React.createElement('h3',null,'Ready for a first reader?'),
        React.createElement('p',{className:'editor-help'},'Publishing creates a public version. Saved playthroughs keep their existing version; future players get this one.'),
        React.createElement('ul',{className:'publish-checklist'},
          React.createElement('li',null,dirty?'Save your unsaved changes first.':'✓ Draft changes are saved.'),
          React.createElement('li',null,characters.some(c=>c.is_ai)?'✓ At least one AI character is ready.':'Add an AI character in Cast before publishing.'),
          missingAdultAges.length>0&&React.createElement('li',{role:'alert'},`Set an adult age (18+) in Cast for: ${missingAdultAges.map(c=>c.name).join(', ')}.`),
          React.createElement('li',null,`${characters.length} characters · ${lore.length} lore entries`)),
        lastPublished&&React.createElement('p',{role:'status'},`Published version ${lastPublished}. You can publish a new version after editing.`),
        React.createElement('button',{className:'btn-primary',onClick:()=>setPublishConfirm(true),disabled:saving||dirty||missingAdultAges.length>0||!characters.some(c=>c.is_ai)},'Publish public version')
      ),

      // ---- Modals ----
      charModal && React.createElement(CharacterModal, {
        scenarioId,
        character: charModal === 'new' ? null : charModal,
        onSave: (c) => {
          if (charModal === 'new') setCharacters(prev => [...prev, c]);
          else setCharacters(prev => prev.map(x => x.id === c.id ? c : x));
          setCharModal(null);
          toast.success('Character saved.');
        },
        onClose: () => setCharModal(null),
      }),

      loreModal && React.createElement(LoreModal, {
        scenarioId,
        lore: loreModal === 'new' ? null : loreModal,
        onSave: (l) => {
          if (loreModal === 'new') setLore(prev => [...prev, l]);
          else setLore(prev => prev.map(x => x.id === l.id ? l : x));
          setLoreModal(null);
          toast.success('Lore saved.');
        },
        onClose: () => setLoreModal(null),
      }),

      publishConfirm && React.createElement(ConfirmDialog, {
        message: 'Publish the saved draft to the public catalog? Existing playthroughs keep their current version.',
        confirmLabel: 'Publish',
        onConfirm: handlePublish,
        onCancel: () => setPublishConfirm(false),
      }),

      deleteChar && React.createElement(ConfirmDialog, {
        message: `Remove "${deleteChar.name}" from the cast?`,
        confirmLabel: 'Remove',
        danger: true,
        onConfirm: () => handleDeleteChar(deleteChar.id),
        onCancel: () => setDeleteChar(null),
      }),

      deleteLore && React.createElement(ConfirmDialog, {
        message: `Remove lore entry "${deleteLore.keyword}"?`,
        confirmLabel: 'Remove',
        danger: true,
        onConfirm: () => handleDeleteLore(deleteLore.id),
        onCancel: () => setDeleteLore(null),
      })
    );
  }

  if (!window.RPScreens) window.RPScreens = {};
  window.RPScreens.ScenarioEditor = ScenarioEditor;
})();
