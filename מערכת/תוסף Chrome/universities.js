// universities.js — Moodle sites the settings page offers by name. Every address was checked to be a Moodle site
// (its own login page, or a sign-on that returns to it) on 3.11.2026. Any other Moodle works too: "אחר" + its address.
// login: the page the nightly download opens. "/my/" is the Moodle dashboard: signed in, it opens; otherwise Moodle
// sends you to its sign-in (often the university's single sign-on) and back.
const UNIVERSITIES = [
  { name: 'אוניברסיטת אריאל', site: 'https://moodlearn.ariel.ac.il', login: '/auth/multioauth/login.php?userType=student' },
  { name: 'אוניברסיטת בן-גוריון', site: 'https://moodle.bgu.ac.il', login: '/moodle/my/' },
  { name: 'אוניברסיטת בר-אילן', site: 'https://lemida.biu.ac.il', login: '/my/' },
  { name: 'הטכניון', site: 'https://moodle26.technion.ac.il', login: '/my/' },
  { name: 'האוניברסיטה הפתוחה', site: 'https://opal.openu.ac.il', login: '/my/' },
  { name: 'המרכז האקדמי לב (JCT)', site: 'https://moodle.jct.ac.il', login: '/my/' },
  { name: 'עזריאלי – המכללה האקדמית להנדסה ירושלים', site: 'https://moodle.jce.ac.il', login: '/my/' },
  { name: 'המכללה האקדמית להנדסה סמי שמעון (SCE)', site: 'https://moodle.sce.ac.il', login: '/my/' },
  { name: 'המכללה למינהל (COLMAN)', site: 'https://moodle.colman.ac.il', login: '/my/' },
  { name: 'המכללה האקדמית אחוה', site: 'https://moodle.achva.ac.il', login: '/my/' },
  { name: 'המכללה האקדמית כנרת', site: 'https://moodle.kinneret.ac.il', login: '/my/' },
  { name: 'המרכז האקדמי רופין', site: 'https://moodle.ruppin.ac.il', login: '/my/' },
  { name: 'המכללה האקדמית גליל מערבי', site: 'https://moodle.wgalil.ac.il', login: '/my/' },
  { name: 'מכללת לוינסקי-וינגייט', site: 'https://moodle.levinsky.ac.il', login: '/my/' },
];
