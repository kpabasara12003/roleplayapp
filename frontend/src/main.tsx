// src/main.tsx — Mounts App to #root, wraps with providers

(function() {
  const { ConversationStoreProvider } = window.RPConvStore;
  const { ToastProvider } = window.RPComponents;
  const { App } = window.RPApp;

  function ThemeSwitch() {
    const [theme,setTheme]=React.useState(window.RPTheme.getChoice());
    React.useEffect(()=>window.RPTheme.subscribe(setTheme),[]);
    return React.createElement('label',{className:'theme-switch'},
      React.createElement('span',null,'Appearance'),
      React.createElement('select',{'aria-label':'Appearance',value:theme,onChange:e=>window.RPTheme.setChoice(e.target.value)},
        React.createElement('option',{value:'light'},'Light'),React.createElement('option',{value:'dark'},'Dark'),React.createElement('option',{value:'system'},'System')));
  }
  function Root() {
    return React.createElement(
      ConversationStoreProvider,
      null,
      React.createElement(
        ToastProvider,
        null,
        React.createElement(React.Fragment,null,React.createElement(ThemeSwitch),React.createElement(App, null))
      )
    );
  }

  const container = document.getElementById('root');
  const root = ReactDOM.createRoot(container);
  root.render(React.createElement(Root, null));
})();
