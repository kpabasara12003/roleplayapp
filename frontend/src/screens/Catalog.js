// src/screens/Catalog.tsx → window.RPScreens.Catalog

(function() {
  const { useState, useEffect, useCallback, useRef } = React;
  const { EmptyState, ErrorBanner, LoadingWrap, Modal } = window.RPComponents;
  const { useToast } = window.RPComponents;
  const Api = window.RPApi;

  function StartStoryModal({ scenario, onStart, onClose }) {
    const toast = useToast();
    const [aiCharId, setAiCharId]       = useState('');
    const [personaId, setPersonaId]     = useState('');
    const [responseLen, setResponseLen] = useState('medium');
    const [personas, setPersonas]       = useState([]);
    const [loading, setLoading]         = useState(false);
    const [err, setErr]                 = useState(null);
    const submittingRef                 = useRef(false);
    const requestIdRef                  = useRef(crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);

    const allCast = (scenario.definition && scenario.definition.cast) || scenario.cast || [];
    const aiChars = allCast.filter(c => c.is_ai);

    useEffect(() => {
      if (aiChars.length > 0) setAiCharId(aiChars[0].id);
      Api.getPersonas().then(p => {
        const list = Array.isArray(p) ? p : (p.personas || p.items || []);
        setPersonas(list);
      }).catch(() => {});
    }, []);

    async function handleStart() {
      if (submittingRef.current) return;
      if (!aiCharId) { setErr({ message: 'Please select an AI character.' }); return; }
      submittingRef.current = true;
      setLoading(true);
      setErr(null);
      try {
        const payload = {
          scenario_id: scenario.id,
          ai_character_id: aiCharId,
          request_id: requestIdRef.current,
          preferences: { response_length: responseLen },
        };
        if (personaId) payload.persona_id = personaId;
        const result = await Api.startChat(payload);
        const convId = result.conversation_id || result.id;
        onStart(convId);
      } catch (err) {
        submittingRef.current = false;
        setErr(err);
      } finally {
        setLoading(false);
      }
    }

    const footer = React.createElement(
      React.Fragment, null,
      React.createElement('button', { className: 'btn-secondary', onClick: onClose, disabled: loading }, 'Cancel'),
      React.createElement('button', { className: 'btn-primary', onClick: handleStart, disabled: loading || !aiCharId },
        loading ? 'Starting...' : 'Start Story')
    );

    return React.createElement(
      Modal, { title: `Start: ${scenario.title}`, onClose, footer, busy:loading },
      React.createElement(ErrorBanner, { error: err }),
      aiChars.length === 0
        ? React.createElement('p', { style: { color: 'var(--color-text-muted)' } }, 'No AI characters defined for this scenario.')
        : React.createElement(
            'div', null,
            React.createElement('div', { className: 'input-group' },
              React.createElement('label', { className: 'label', htmlFor: 'start-ai-char' }, 'AI Character'),
              React.createElement(
                'select', { id: 'start-ai-char', className: 'select', value: aiCharId, onChange: e => setAiCharId(e.target.value) },
                aiChars.map(c => React.createElement('option', { key: c.id, value: c.id }, c.name))
              )
            ),
            React.createElement('div', { className: 'input-group' },
              React.createElement('label', { className: 'label', htmlFor: 'start-persona' }, 'Your Persona (optional)'),
              React.createElement(
                'select', { id: 'start-persona', className: 'select', value: personaId, onChange: e => setPersonaId(e.target.value) },
                React.createElement('option', { value: '' }, 'No persona (default)'),
                personas.map(p => React.createElement('option', { key: p.id, value: p.id }, p.name))
              )
            ),
            React.createElement('div', { className: 'input-group' },
              React.createElement('label', { className: 'label', htmlFor: 'start-length' }, 'Response Length'),
              React.createElement(
                'select', { id: 'start-length', className: 'select', value: responseLen, onChange: e => setResponseLen(e.target.value) },
                React.createElement('option', { value: 'short' }, 'Short'),
                React.createElement('option', { value: 'medium' }, 'Medium'),
                React.createElement('option', { value: 'long' }, 'Long')
              )
            )
          )
    );
  }

  function Catalog({ onNavigate }) {
    const h=React.createElement;
    const emptyFilters={genre:'',tone:'',life_stage:'',gender:'',mode:''};
    const [scenarios,setScenarios]=useState([]),[loading,setLoading]=useState(true),[error,setError]=useState(null);
    const [searchType,setSearchType]=useState('hybrid'),[searchWarning,setSearchWarning]=useState(null);
    const [query,setQuery]=useState(''),[filters,setFilters]=useState(emptyFilters),[terms,setTerms]=useState([]);
    const [startModal,setStartModal]=useState(null),[hasMore,setHasMore]=useState(false),[lastId,setLastId]=useState(null);
    const sequence=useRef(0),mounted=useRef(true),pageBusy=useRef(false);
    const filterKey=JSON.stringify(filters);
    useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;sequence.current++;};},[]);
    async function load(before,version) {
      if(before&&pageBusy.current)return;
      pageBusy.current=true;setLoading(true);setError(null);
      try {
        const params={limit:24,q:query.trim(),...Object.fromEntries(Object.entries(filters).filter(([,v])=>v)),...(before?(query.trim()?{cursor:before}:{before}):{}),...(query.trim()?{search_type:searchType}:{})};
        const [data,options]=await Promise.all([(query.trim()?Api.searchCatalog(params):Api.getCatalog(params)),terms.length?Promise.resolve(terms):Api.getCatalogFilters()]);
        if(!mounted.current||version!==sequence.current)return;
        setTerms(options);
        setSearchWarning(data.warning||null);
        const page=Array.isArray(data)?data:data.items;
        const rows=page.map(row=>({...row.definition,...row,definition:row.definition}));
        setScenarios(old=>before?[...old,...rows.filter(r=>!old.some(o=>o.id===r.id))]:rows);
        setHasMore(query.trim()?!!data.next_cursor:rows.length===24);setLastId(query.trim()?data.next_cursor:rows.length?rows[rows.length-1].id:null);
      } catch(err){if(mounted.current&&version===sequence.current)setError(err);}
      finally{if(mounted.current&&version===sequence.current){pageBusy.current=false;setLoading(false);}}
    }
    useEffect(()=>{
      const version=++sequence.current;pageBusy.current=false;setLoading(true);setError(null);setSearchWarning(null);setScenarios([]);setHasMore(false);setLastId(null);
      const timer=setTimeout(()=>load(null,version),300);
      return()=>{clearTimeout(timer);sequence.current++;};
    },[query,filterKey,searchType]);
    const shown=scenarios;
    const activeCount=Object.values(filters).filter(Boolean).length+(query.trim()?1:0);
    function clearFilters(){setQuery('');setFilters(emptyFilters);}
    function filterSelect(kind,label){return h('div',{className:'discovery-filter',key:kind},h('label',{className:'label',htmlFor:'filter-'+kind},label),h('select',{id:'filter-'+kind,className:'select',value:filters[kind],onChange:e=>setFilters(f=>({...f,[kind]:e.target.value}))},h('option',{value:''},'Any '+label.toLowerCase()),terms.filter(t=>t.kind===kind&&t.slug!=='any').map(t=>h('option',{key:t.slug,value:t.slug},t.label))));}
    function labelFor(kind,slug){return terms.find(t=>t.kind===kind&&t.slug===slug)?.label||slug.replaceAll('_',' ');}
    return h('div',{className:'discover-page'},
      h('header',{className:'studio-heading'},h('span',{className:'eyebrow'},'THE STORY STUDIO'),h('span',{className:'edition'},'MAKE BELIEVE. MAKE IT YOURS.')),
      h('section',{className:'discover-hero'},
        h('div',null,h('span',{className:'eyebrow'},'A LITTLE CHEMISTRY. A WHOLE NEW STORY.'),h('h1',null,'Your next life',h('br'),h('em',null,'starts with a word.')),
          h('p',null,'Find a slow-burn connection, a cozy everyday escape or an adventure worth sharing. Choose the cast and the feeling. Make the next chapter yours.'),
          h('div',{className:'hero-actions'},h('button',{className:'btn-primary',onClick:()=>onNavigate('MyScenarios')},'Create a scenario',h('span',{'aria-hidden':true},' ↗')),h('button',{className:'hero-link',onClick:()=>onNavigate('SavedStories')},'Continue your story →'))),
        h('div',{className:'hero-art','aria-hidden':true},h('span',{className:'orbit orbit-one'}),h('span',{className:'orbit orbit-two'}),h('span',{className:'orbit-core'},'f.'),h('span',{className:'orbit-caption'},'ENDLESS POSSIBILITIES / ONE YOU'))),
      h('section',{className:'worlds-section','aria-label':'Explore roleplay scenarios'},
        h('div',{className:'explore-heading'},h('div',null,h('span',{className:'eyebrow'},'CHOOSE YOUR FIRST CHAPTER'),h('h2',null,'Somewhere else awaits.')),h('label',{className:'world-search'},h('span',{'aria-hidden':true},'⌕'),h('input',{type:'search',value:query,onChange:e=>setQuery(e.target.value),placeholder:'A slow romance in a rainy seaside town…',maxLength:200,'aria-label':'Search all published scenarios','aria-describedby':'catalog-search-help'}))),
        h('p',{id:'catalog-search-help',className:'editor-help'},'Describe the story you want, or search a title or creator name. Hybrid combines meaning with keyword matches.'),
        h('div',{className:'search-modes','aria-label':'Search method'},[['hybrid','Hybrid · recommended'],['semantic','Similar themes'],['keyword','Title & keywords']].map(([value,label])=>h('button',{key:value,className:searchType===value?'filter-chip selected':'filter-chip','aria-pressed':searchType===value,onClick:()=>setSearchType(value)},label))),
        searchWarning&&h('p',{className:'editor-help',role:'status'},searchWarning),
        h('div',{className:'world-filters discovery-genres','aria-label':'Story genre'},
          [{slug:'',label:'All scenarios'},...terms.filter(t=>t.kind==='genre')].map(t=>h('button',{key:t.slug,className:filters.genre===t.slug?'filter-chip selected':'filter-chip','aria-pressed':filters.genre===t.slug,onClick:()=>setFilters(f=>({...f,genre:t.slug}))},t.label))),
        h('div',{className:'discovery-controls'},filterSelect('gender','Character gender'),filterSelect('tone','Tone'),filterSelect('life_stage','Life stage'),
          h('div',{className:'discovery-filter'},h('label',{className:'label',htmlFor:'filter-mode'},'Play style'),h('select',{id:'filter-mode',className:'select',value:filters.mode,onChange:e=>setFilters(f=>({...f,mode:e.target.value}))},h('option',{value:''},'Any play style'),h('option',{value:'freeform'},'Freeform'),h('option',{value:'structured'},'Guided adventure')))),
        h('div',{className:'world-toolbar'},h('span',{className:'world-count',role:'status','aria-live':'polite'},loading?'Finding scenarios…':`${shown.length}${hasMore?'+':''} matching ${shown.length===1?'scenario':'scenarios'} loaded`),activeCount>0&&h('button',{className:'btn-ghost btn-sm',onClick:clearFilters},`Clear filters (${activeCount})`)),
        h('p',{className:'editor-help'},'Gender filters the AI characters in a published cast. Young-adult and romance categories use adult characters (18+).'),
        h(ErrorBanner,{error,onDismiss:()=>setError(null)}),error&&h('button',{className:'btn-secondary',disabled:loading,onClick:()=>load(error?.status===410?null:lastId&&scenarios.length?lastId:null,sequence.current)},'Try again'),
        loading&&!scenarios.length?h(LoadingWrap):shown.length?h('div',{className:'world-grid'},shown.map((s,i)=>h('article',{className:`world-card tone-${i%3}`,key:s.id},
          h('div',{className:'world-card-art','aria-hidden':true},h('span',{className:'world-number'},String(i+1).padStart(2,'0')),h('span',{className:'world-emblem'},['◇','◎','✳'][i%3]),h('span',{className:'world-place'},s.place||'Character-led roleplay')),
          h('div',{className:'world-card-copy'},h('div',{className:'world-card-kicker'},h('span',null,s.rules?.mode==='structured'?'GUIDED ADVENTURE':'FREEFORM ROLEPLAY'),h('span',null,'↗')),h('h3',null,s.title),h('p',{className:'world-author'},'By '+(s.creator||'a storyteller')),h('div',{className:'discovery-badges'},(s.discovery?.genres||[]).map(g=>h('span',{className:'badge',key:g},labelFor('genre',g))),(s.discovery?.tones||[]).map(t=>h('span',{className:'badge',key:t},labelFor('tone',t)))),h('p',null,s.introduction||'A new story, waiting for your first move.'),h('div',{className:'world-cast'},h('span',{className:'cast-initial'},s.definition?.cast?.find(c=>c.is_ai)?.name?.charAt(0)||'?'),h('span',null,s.definition?.cast?.filter(c=>c.is_ai).map(c=>c.name).slice(0,2).join(' & ')||'Meet the characters')),
          h('button',{className:'world-enter',onClick:()=>setStartModal(s)},'Start roleplay',h('span',{'aria-hidden':true},'→')))))):h(EmptyState,{message:activeCount?'No scenarios match this combination. Try fewer filters or different search words.':'Your next adventure is still being written.',action:{label:activeCount?'Clear filters':'Create a scenario',onClick:activeCount?clearFilters:()=>onNavigate('MyScenarios')}}),
        hasMore&&h('button',{className:'btn-secondary load-worlds',disabled:loading,onClick:()=>load(lastId,sequence.current)},loading?'Loading…':'Explore more scenarios')),
      h('footer',{className:'studio-footer'},h('span',null,'No script. Just possibility.'),h('span',null,'YOUR CHOICES LEAVE A MARK.')),
      startModal&&h(StartStoryModal,{scenario:startModal,onStart:id=>{setStartModal(null);onNavigate('ChatScreen',{conversationId:id});},onClose:()=>setStartModal(null)})
    );
  }
  if(!window.RPScreens)window.RPScreens={};window.RPScreens.Catalog=Catalog;
})();
