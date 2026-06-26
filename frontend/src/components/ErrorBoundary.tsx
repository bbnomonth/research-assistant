import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Button, Result } from 'antd';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('[ErrorBoundary]', error, info);
  }

  handleReload = () => {
    window.location.reload();
  };

  handleReset = () => {
    this.setState({ error: null });
  };

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <Result
        status="error"
        title="页面出现了未捕获的错误"
        subTitle={this.state.error.message}
        extra={
          <>
            <Button type="primary" onClick={this.handleReload}>
              刷新页面
            </Button>
            <Button onClick={this.handleReset} style={{ marginLeft: 8 }}>
              返回上一页
            </Button>
          </>
        }
      />
    );
  }
}
