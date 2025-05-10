document.addEventListener("DOMContentLoaded", () => {
  const grApp = () => gradioApp?.() || document;
  const icon = grApp().querySelector("#aec-link-icon");
  const dlg = grApp().querySelector("#aec-auth-dialog");
  const tbl = () => grApp().querySelector("table[data-testid='queue_tbl']")     // gradio 4
                    || grApp().querySelector("table");                          // gradio 3

  if (icon && dlg){
    icon.addEventListener("click", () => dlg.style.display = dlg.style.display ? "" : "block");
    dlg.querySelector("button:contains('Close')")?.addEventListener("click", () => dlg.style.display = "");
  }

  async function pollHealth(){
    try{
      const base = localStorage.getItem("aec-base");
      const key  = localStorage.getItem("aec-key");
      if(!base){ icon?.classList.remove("connected"); return }
      const r = await fetch(`${base.replace(/\/$/,"")}/health`, { headers:{ "x-api-key":key||"" } });
      if(r.ok){ icon?.classList.add("connected"); }
      else    { icon?.classList.remove("connected"); }
    }catch{ icon?.classList.remove("connected"); }
  }
  setInterval(pollHealth, 15000); pollHealth();

  const decorate = () => {
    const rows = tbl()?.querySelectorAll("tbody tr") || [];
    let busy = false;
    rows.forEach(row=>{
      const cells = row.children;
      if(cells.length < 4) return;
      const state = cells[2].innerText.trim();
      const prog  = Number(cells[3].innerText) || 0;
      cells[3].classList.add("aec-progress");
      cells[3].style.setProperty("--p", prog + "%");
      cells[3].innerHTML = `<span>${prog}%</span>`;
      if(state === "DOWNLOADING"){ busy = true; }
    });
    icon?.classList.toggle("busy", busy);
  };

  const obs = new MutationObserver(decorate);
  if(tbl()){ obs.observe(tbl(), { childList:true, subtree:true }); }
  decorate();
});
