import React,{useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Search,GraduationCap,Sparkles,Star,ArrowRight,SlidersHorizontal,GitCompareArrows,UserRound,LogOut,X,BookOpen,MessageSquare,Heart} from 'lucide-react';
import {api,getToken,setToken} from './api';
import './style.css';

const fullName=p=>p?`${p.first_name} ${p.last_name}`:'Unknown professor';
const initials=p=>p?`${p.first_name?.[0]||''}${p.last_name?.[0]||''}`.toUpperCase():'P';
const fmt=n=>n==null?'—':Number(n).toFixed(1);

function App(){
 const [page,setPage]=useState('discover'),
    [query,setQuery]=useState(''),
    [department,setDepartment]=useState('All departments'),
    [sort,setSort]=useState('rating');

 const [professors,setProfessors]=useState([]),
    [stats,setStats]=useState({}),
    [selected,setSelected]=useState(null),
    [reviews,setReviews]=useState([]),
    [summary,setSummary]=useState(null),
    [compareIds,setCompareIds]=useState([]),
    [comparison,setComparison]=useState(null),
    [courseFilter,setCourseFilter]=useState('');

 const [user,setUser]=useState(null),
    [authOpen,setAuthOpen]=useState(false),
    [authMode,setAuthMode]=useState('login'),
    [email,setEmail]=useState(''),
    [password,setPassword]=useState(''),
    [name,setName]=useState('');

 const [message,setMessage]=useState(''),
    [loading,setLoading]=useState(false),
    [recommendations,setRecommendations]=useState([]),
    [reviewText,setReviewText]=useState(''),
    [reviewRating,setReviewRating]=useState(5),
    [reviewDifficulty,setReviewDifficulty]=useState(3),
    [reviewCourse,setReviewCourse]=useState(''),
    [takeAgain,setTakeAgain]=useState(''),
    [editingReview,setEditingReview]=useState(null);

 const [options,setOptions]=useState([]),
    [preferences,setPreferences]=useState([]),
    [savedPrefs,setSavedPrefs]=useState(false);

 const showError=e=>setMessage(e.message||String(e));


 async function loadProfessors(q='',course=''){setLoading(true);setMessage('');
    try{const params=new URLSearchParams({limit:'100'});
    if(q)params.set('q',q);
    if(course)params.set('course',course);
    const list=await api(`/professors?${params}`);
    setProfessors(list);
    const details=await Promise.allSettled(list.map(p=>api(`/professors/${p.id}`)));
    setStats(Object.fromEntries(details.map((r,i)=>[list[i].id,r.status==='fulfilled'?r.value.stats:null])));}
    catch(e){showError(e);}finally{setLoading(false);}}

 useEffect(()=>{loadProfessors();
    if(getToken())api('/me').then(setUser).catch(()=>setToken(null));api('/preferences/options').then(setOptions).catch(()=>{});},[]);
 
 async function openProfessor(p){setPage('profile');
    setSelected(p);
    setSummary(null);
    setReviews([]);
    setMessage('');
    try{const [detail,list]=await Promise.all([api(`/professors/${p.id}`),api(`/professors/${p.id}/reviews`)]);
    setSelected(detail);
    setReviews(list);}
    catch(e){showError(e);}}

 async function loadSummary()
    {try{setSummary(await api(`/professors/${selected.id}/summary`));}
    catch(e){showError(e);}}

 async function submitAuth(e){e.preventDefault();
    setMessage('');
    try{if(authMode==='register')await api('/auth/register',{method:'POST',body:{email,password,display_name:name}});
    const result=await api('/auth/login',{method:'POST',body:{username:email,password},form:true});
    setToken(result.access_token);
    setUser(await api('/me'));
    setAuthOpen(false);
    setPassword('');}
    catch(e){showError(e);}}

 async function submitReview(e){e.preventDefault();
    setMessage('');
    try{const body={quality:Number(reviewRating),difficulty:Number(reviewDifficulty),text:reviewText,...(!editingReview?{course_code:reviewCourse}:{})};
    if(takeAgain!=='')body.would_take_again=takeAgain==='yes';
    await api(editingReview?`/reviews/${editingReview}`:`/professors/${selected.id}/reviews`,{method:editingReview?'PATCH':'POST',body});
    setEditingReview(null);
    setReviewText('');
    setReviewCourse('');
    setTakeAgain('');
    setReviews(await api(`/professors/${selected.id}/reviews`));
    const detail=await api(`/professors/${selected.id}`);
    setSelected(detail);
    setStats(old=>({...old,[selected.id]:detail.stats}));
    setSummary(null);
    setMessage('Review saved.');}
    catch(e){showError(e);}}

 async function deleteReview(id){if(!window.confirm('Delete your review?'))return;
    try{await api(`/reviews/${id}`,{method:'DELETE'});
    setReviews(await api(`/professors/${selected.id}/reviews`));
    const detail=await api(`/professors/${selected.id}`);
    setSelected(detail);setStats(old=>({...old,[selected.id]:detail.stats}));
    setSummary(null);setMessage('Review deleted.');}
    catch(e){showError(e);}}

 function editReview(r){setEditingReview(r.id);
    setReviewText(r.text);
    setReviewRating(r.quality);
    setReviewDifficulty(r.difficulty);
    setReviewCourse(r.course_code);
    setTakeAgain(r.would_take_again==null?'':r.would_take_again?'yes':'no');}

 async function doCompare(){if(compareIds.length!==2)return;
    try{const params=new URLSearchParams({a:compareIds[0],b:compareIds[1]});
    if(courseFilter)params.set('course',courseFilter);setComparison(await api(`/compare?${params}`));
    setPage('compare');setMessage('');}
    catch(e){showError(e);}}

 async function loadPreferences(){if(!user){setAuthOpen(true);
    return;}
    setPage('recommendations');
    setMessage('');
    try{const current=await api('/me/preferences');
    setPreferences(current);
    setSavedPrefs(current.length>0);
    if(current.length)await getRecommendations();
    else setRecommendations([]);}
    catch(e){showError(e);}}

 async function getRecommendations()
    {try{const result=await api('/me/recommendations?min_reviews=1');
    setRecommendations(result);}
    catch(e){showError(e);}}

 function updatePref(dim,direction)
    {setSavedPrefs(false);
    setPreferences(old=>direction==='none'?old.filter(p=>p.dimension!==dim):[...old.filter(p=>p.dimension!==dim),{dimension:dim,direction,importance:2}]);}

 async function savePreferences()
    {try{await api('/me/preferences',{method:'PUT',body:{preferences}});
    setSavedPrefs(true);
    setMessage('Preferences saved.');
    await getRecommendations();}
    catch(e){showError(e);}}


 const departments=['All departments',...new Set(professors.map(p=>p.department).filter(Boolean))];
 const visible=professors.filter(p=>department==='All departments'||p.department===department).sort((a,b)=>sort==='rating'?(stats[b.id]?.avg_quality??-1)-(stats[a.id]?.avg_quality??-1):sort==='reviews'?(stats[b.id]?.review_count??0)-(stats[a.id]?.review_count??0):(stats[b.id]?.avg_difficulty??-1)-(stats[a.id]?.avg_difficulty??-1));
 const toggleCompare=id=>setCompareIds(old=>old.includes(id)?old.filter(x=>x!==id):old.length<2?[...old,id]:[old[1],id]);
 const chosen=professors.filter(p=>compareIds.includes(p.id));


return <>
<header className="topbar">
    <div className="shell nav">
        <button className="logo" onClick={()=>setPage('discover')}>
            <span className="logo-mark"><GraduationCap size={22}/></span> 
            professor<span className="logo-dot">.io</span>
        </button>
        <nav>
            <button className={page==='discover'?'active':''} onClick={()=>setPage('discover')}>Explore</button>
            <button className={page==='compare'?'active':''} onClick={()=>setPage('compare')}>Compare</button>
            <button className={page==='recommendations'?'active':''} onClick={loadPreferences}>For you <Sparkles size={14}/></button>
        </nav>
        <div className="account">
            {user?<button className="ghost" onClick={()=>{setToken(null);setUser(null);setRecommendations([]);setPage('discover');}}>
                <LogOut size={16}/> {user.display_name} · Log out
            </button>:
            <button className="primary small" onClick={()=>setAuthOpen(true)}>Log in / Sign up <ArrowRight size={15}/></button>}
        </div>
    </div>
</header>

{page==='discover'&&<>
<section className="hero">
    <div className="shell hero-content">
        <div className="eyebrow">
            <Sparkles size={14}/> SMARTER COURSE CHOICES START HERE
        </div>
        <h1>Find the professor<br/>
            who <em>fits you.</em>
        </h1>
        <p>Real student reviews. AI-powered insights. Personalized matches. Everything you need to choose your next great class.</p>
        <form className="hero-search" onSubmit={e=>{e.preventDefault();loadProfessors(query,courseFilter);}}>
            <Search size={21}/>
            <input aria-label="Search professor names" placeholder="Search professor names..." value={query} onChange={e=>setQuery(e.target.value)}/>
            <button className="primary" type="submit">Search <ArrowRight size={17}/></button>
        </form>
        <div className="hero-foot">
            <span><Star size={15}/> Student-powered reviews</span>
            <span><Sparkles size={15}/> AI-generated insights</span>
            <span><Heart size={15}/> Personalized for you</span>
        </div>
    </div>
    <div className="hero-decoration">P
        <span>.</span>
    </div>
</section>
<main className="shell main">
    <div className="section-top">
        <div>
            <div className="eyebrow dark">EXPLORE YOUR OPTIONS</div>
            <h2>Discover professors</h2>
            <p>Browse ratings and find the teaching style that works for you.</p>
        </div>
        <button className="outline" onClick={loadPreferences}><Sparkles size={16}/> Get matched</button>
    </div>
    <div className="filters">
        <div className="filter-title">
            <SlidersHorizontal size={17}/> Filters
        </div>
        <label>Department
            <select value={department} onChange={e=>setDepartment(e.target.value)}>{departments.map(d=><option key={d}>{d}</option>)}</select>
        </label>
        <label>Course code
            <input placeholder="e.g. CS101" value={courseFilter} onChange={e=>setCourseFilter(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')loadProfessors(query,courseFilter);}}/>
        </label>
        <button className="outline" onClick={()=>loadProfessors(query,courseFilter)}>Apply</button>
        <label>Sort by
            <select value={sort} onChange={e=>setSort(e.target.value)}>
                <option value="rating">Highest rated</option>
                <option value="reviews">Most reviewed</option>
                <option value="difficulty">Most difficult</option>
            </select>
        </label>
        <span className="result-count">{visible.length} professors</span>
    </div>
    {loading?<p>Loading professors...</p>:
    <div className="cards">{visible.map(p=>
        <article className="prof-card" key={p.id}>
            <div className="card-top">
                <div className="avatar">{initials(p)}</div>
                <div className="rating"><Star size={16} fill="currentColor"/> {fmt(stats[p.id]?.avg_quality)}</div>
            </div>
            <h3>{fullName(p)}</h3>
            <div className="dept">{p.department}</div>
            <div className="metrics">
                <div><strong>{fmt(stats[p.id]?.avg_difficulty)}</strong>
                    <span>Difficulty</span>
                </div>
                <div><strong>{stats[p.id]?.review_count??'—'}</strong>
                    <span>Reviews</span>
                </div>
                <div><strong>{p.school}</strong>
                    <span>School</span>
                </div>
            </div>
            <div className="card-actions">
                <button className="card-link" onClick={()=>openProfessor(p)}>View profile <ArrowRight size={16}/></button>
                <button className={'compare-toggle '+(compareIds.includes(p.id)?'chosen':'')} onClick={()=>toggleCompare(p.id)}><GitCompareArrows size={15}/>{compareIds.includes(p.id)?'Selected':'Compare'}</button>
            </div>
        </article>)}
    </div>}{!loading&&visible.length===0&&
    <div className="empty">No professors found. Try another search or load sample data.</div>}
</main></>}

{page==='profile'&&selected&&
<main className="shell inner">
    <button className="back" onClick={()=>setPage('discover')}>← Back to professors</button>
    <div className="profile-heading">
        <div className="avatar large">{initials(selected)}</div>
        <div>
            <div className="eyebrow dark">PROFESSOR PROFILE</div>
            <h1>{fullName(selected)}</h1>
            <p>{selected.department} · {selected.school}</p>
        </div>
        <div className="profile-score"><Star fill="currentColor" size={24}/> {fmt(selected.stats?.avg_quality)}<small>Overall rating</small></div>
    </div>
    <div className="two-col">
        <section className="panel">
            <h2><Sparkles size={21}/> AI review summary</h2>
            <p>Discover strengths, concerns, workload and grading from student feedback.</p>
            <button className="primary" onClick={loadSummary}>View AI summary</button>
            {summary&&(summary.summary?
            <div className="summary">
                <p>{summary.summary.overview}</p>
                <h3>Strengths</h3>
                <ul>{summary.summary.strengths.map((x,i)=>
                    <li key={i}>{x}</li>)}
                </ul>
                <h3>Criticisms</h3>
                <ul>{summary.summary.criticisms.map((x,i)=>
                    <li key={i}>{x}</li>)}
                </ul>
                <p><strong>Workload:</strong> {summary.summary.workload}</p>
                <p><strong>Grading:</strong> {summary.summary.grading}</p>
                <p><strong>Best for:</strong> {summary.summary.best_for}</p>
            </div>:
            <p>{summary.note||'Summary unavailable.'}</p>)}
        </section>
        <section className="panel">
            <h2><BookOpen size={21}/> At a glance</h2>
            <div className="fact">
                <span>Difficulty</span>
                <strong>{fmt(selected.stats?.avg_difficulty)}</strong>
            </div>
            <div className="fact">
                <span>Student reviews</span>
                <strong>{selected.stats?.review_count??'—'}</strong>
            </div>
            <div className="fact">
                <span>Would take again</span>
                <strong>{selected.stats?.would_take_again_pct==null?'—':`${fmt(selected.stats.would_take_again_pct)}%`}</strong>
            </div>
            <h3>Teaching traits</h3>
            {selected.stats?.traits?.map(t=>
            <div className="fact" key={t.dimension}>
                <span>{t.label}</span>
                <strong>{t.evidence?`${Math.round(t.value*100)}% (${t.evidence})`:'Insufficient data'}</strong>
            </div>)}
        </section>
    </div>
    <section className="panel spaced">
        <h2><MessageSquare size={21}/> Student reviews</h2>
        {reviews.length===0?
        <p>No reviews yet.</p>:
        reviews.map(r=>
        <div className="review" key={r.id}>
            <div>
                <strong>{r.course_code}</strong>
                <span className="rating"><Star size={14} fill="currentColor"/> {r.quality}/5 · Difficulty {r.difficulty}/5</span>
            </div>
            <p>{r.text}</p>
            {r.tags.length>0&&
            <p>Tags: {r.tags.join(', ')}</p>}
            {r.is_mine&&
            <div className="card-actions">
                <button className="outline" onClick={()=>editReview(r)}>Edit</button>
                <button className="outline" onClick={()=>deleteReview(r.id)}>Delete</button>
            </div>}
        </div>)}
    </section>
    <section className="panel spaced">
        <h2>{editingReview?'Edit your review':'Write a review'}</h2>
        {!user?<p>
            <button className="text-button" onClick={()=>setAuthOpen(true)}>Log in</button>
             to share your experience.
        </p>:
        <form className="review-form" onSubmit={submitReview}>
            <label>Course code
                <input required minLength={2} maxLength={20} disabled={!!editingReview} placeholder="e.g. CS101" value={reviewCourse} onChange={e=>setReviewCourse(e.target.value)}/>
            </label>
            <label>Quality
                <select value={reviewRating} onChange={e=>setReviewRating(e.target.value)}>{[5,4,3,2,1].map(n=>
                    <option key={n} value={n}>{n} / 5</option>)}
                </select>
            </label>
            <label>Difficulty
                <select value={reviewDifficulty} onChange={e=>setReviewDifficulty(e.target.value)}>{[1,2,3,4,5].map(n=>
                    <option key={n} value={n}>{n} / 5</option>)}
                </select>
            </label>
            <label>Would take again?
                <select value={takeAgain} onChange={e=>setTakeAgain(e.target.value)}>
                    <option value="">Prefer not to say</option>
                    <option value="yes">Yes</option>
                    <option value="no">No</option>
                </select>
            </label>
            <label className="full">Your review (20–3000 characters)
                <textarea required minLength={20} maxLength={3000} rows="4" value={reviewText} onChange={e=>setReviewText(e.target.value)} placeholder="What should other students know?"/>
            </label>
            <button className="primary">{editingReview?'Save changes':'Submit review'}</button>
            {editingReview&&
            <button type="button" className="outline" onClick={()=>{setEditingReview(null);setReviewText('');setReviewCourse('');}}>Cancel edit</button>}
        </form>}
    </section>
</main>}

{page==='compare'&&
<main className="shell inner">
    <div className="eyebrow dark">MAKE A CONFIDENT CHOICE</div>
    <h1>Compare professors</h1>
    <p>Choose two professors from Explore to compare them side by side.</p>
    <div className="comparison-picks">{[0,1].map(i=>
        <div className="pick" key={i}>{fullName(professors.find(p=>p.id===compareIds[i]))}</div>)}
    </div>
    <label>Optional course code 
        <input placeholder="CS101" value={courseFilter} onChange={e=>setCourseFilter(e.target.value)}/>
    </label>
    <p>
        <button className="primary" disabled={compareIds.length!==2} onClick={doCompare}>Compare selected professors <GitCompareArrows size={16}/></button>
    </p>{comparison&&
    <section className="panel spaced">
        <h2>Comparison results</h2>
        <div className="two-col">{['a','b'].map(side=>
            <div key={side}>
                <h3>{fullName(comparison[side].professor)}</h3>
                <p>Quality: {fmt(comparison[side].stats.avg_quality)} / 5</p>
                <p>Difficulty: {fmt(comparison[side].stats.avg_difficulty)} / 5</p>
                <p>Reviews: {comparison[side].stats.review_count}</p>
                {comparison[side].compatibility&&
                <p>Compatibility: {comparison[side].compatibility.score??'—'} / 100 ({comparison[side].compatibility.confidence} confidence)</p>}
            </div>)}
        </div>
        <h3>Teaching trait differences</h3>
        {comparison.dimensions.map(d=>
        <div className="fact" key={d.dimension}>
            <span>{d.label}</span>
            <strong>{d.higher==='insufficient_data'?'Insufficient data':d.higher==='similar'?'Similar':`Higher: ${fullName(comparison[d.higher].professor)}`}</strong>
        </div>)}
        {comparison.narrative?
        <div className="summary">
            <h3>AI comparison</h3>
            <p>{comparison.narrative.overview}</p>
            <h3>Key differences</h3>
            <ul>{comparison.narrative.key_differences.map((x,i)=>
                <li key={i}>{x}</li>)}
            </ul>
            {['a','b'].map(side=>
            <div key={side}>
                <h3>Choose {fullName(comparison[side].professor)} if…</h3>
                <ul>{comparison.narrative[`choose_${side}_if`].map((x,i)=>
                    <li key={i}>{x}</li>)}
                </ul>
            </div>)}
        </div>:
        <p>{comparison.narrative_note||'No AI narrative returned.'}</p>}
    </section>}
</main>}

{page==='recommendations'&&
<main className="shell inner">
    <div className="eyebrow dark">PERSONALIZED FOR YOU</div>
    <h1>Your professor matches</h1>
    <p>Tell us what matters to you. Compatibility measures review-based alignment with your preferences, not your predicted grade.</p>
    <section className="panel spaced">
        <h2>Your teaching preferences</h2>
        {[...new Set(options.map(o=>o.dimension))].map(dim=>{const choices=options.filter(o=>o.dimension===dim);const pref=preferences.find(p=>p.dimension===dim);
            return <div className="fact" key={dim}>
                <span>{choices[0]?.label||dim}</span>
                <select value={pref?.direction||'none'} onChange={e=>updatePref(dim,e.target.value)}>
                    <option value="none">No preference</option>
                    {choices.map(c=>
                    <option key={c.direction} value={c.direction}>{c.prompt}</option>)}
                </select>
                {pref&&<select aria-label={`Importance for ${dim}`} value={pref.importance} onChange={e=>{setSavedPrefs(false);setPreferences(old=>old.map(p=>p.dimension===dim?{...p,importance:Number(e.target.value)}:p));}}>
                    <option value={1}>Nice to have</option>
                    <option value={2}>Important</option>
                    <option value={3}>Very important</option>
                </select>}
            </div>;})}
            <button className="primary" onClick={savePreferences}>Save preferences and find matches</button>
    </section>
    {savedPrefs&&<button className="outline" onClick={getRecommendations}>Refresh recommendations</button>}
    <div className="cards spaced">{recommendations.map(r=>
        <article className="prof-card" key={r.professor.id}>
            <h3>{fullName(r.professor)}</h3>
            <p>{r.professor.department} · {r.professor.school}</p>
            <p>Quality: {fmt(r.avg_quality)} · {r.review_count} reviews</p>
            <p>Compatibility: <strong>{r.compatibility.score==null?'Insufficient data':`${r.compatibility.score}/100`}</strong></p>
            <p>Confidence: <strong>{r.compatibility.confidence}</strong></p>
            {r.compatibility.reasons.map((x,i)=><p key={i}>✓ {x}</p>)}
            {r.compatibility.concerns.map((x,i)=><p key={i}>! {x}</p>)}
            <small>{r.compatibility.disclaimer}</small>
            <p>
                <button className="card-link" onClick={()=>openProfessor(r.professor)}>View profile <ArrowRight size={16}/></button>
            </p>
        </article>)}
    </div>{savedPrefs&&recommendations.length===0&&
    <p className="empty">No matching professors with reviews yet.</p>}
</main>}

{message&&
<div className="toast" role="status">{message}
    <button onClick={()=>setMessage('')} aria-label="Dismiss"><X size={16}/></button>
</div>}

{authOpen&&
<div className="modal-backdrop" onClick={()=>setAuthOpen(false)}>
    <div className="modal" onClick={e=>e.stopPropagation()}>
        <button className="close" onClick={()=>setAuthOpen(false)}><X size={20}/></button>
        <div className="logo-mark">
            <UserRound size={23}/>
        </div>
        <h2>{authMode==='login'?'Welcome back':'Join Professor.io'}</h2>
        <p>{authMode==='login'?'Log in to leave reviews and get personalized matches.':'Create an account to find your best-fit professors.'}</p>
        <form onSubmit={submitAuth}>{authMode==='register'&&
            <label>Name<input required maxLength={80} value={name} onChange={e=>setName(e.target.value)} placeholder="Your name"/></label>}
            <label>Email<input type="email" required value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@university.edu"/></label>
            <label>Password<input type="password" minLength={authMode==='register'?8:undefined} required value={password} onChange={e=>setPassword(e.target.value)} placeholder="Your password"/></label>
            <button className="primary wide">{authMode==='login'?'Log in':'Create account'}</button>
        </form>
        <p className="switch">{authMode==='login'?"Don't have an account? ":'Already have an account? '}
            <button onClick={()=>setAuthMode(authMode==='login'?'register':'login')}>{authMode==='login'?'Sign up':'Log in'}</button>
        </p>
    </div>
</div>}

<footer>
    <div className="shell footer-content">
        <strong>professor
            <span>.io</span>
        </strong>
        <span>Better professors. Better choices.</span>
        <small>Made for students, powered by student voices.</small>
    </div>
</footer></>;

}
createRoot(document.getElementById('root')).render(<App/>);