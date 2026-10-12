import { createHandler } from '../../lib/course-editor.mjs';

export default createHandler();
export const config = {
    rateLimit: { action: 'rate_limit', aggregateBy: 'ip', windowSize: 60, windowLimit: 20 }
};
